from fastapi import APIRouter, Request, Depends, HTTPException, status, Query, Path, Body
from typing import List, Optional, Dict, Any
import numpy as np
from sklearn.decomposition import PCA
from bson import ObjectId
from datetime import datetime, timedelta
import time
from pydantic import BaseModel, EmailStr, Field
import os
import shutil
import asyncio
from services.database import ip_credits_collection, credit_requests_collection
from services.database import ip_hits_collection
from fastapi.responses import JSONResponse
from services.auth import get_current_user, requires_role, get_password_hash, get_user_by_email
from services.database import users_collection, api_usage_collection, transcription_stats_collection, search_trends_collection, user_activity_collection
from services.gemini_key_manager import gemini_key_manager
from services.pinecone_service import index as pinecone_index, init_pinecone
from models.analytics import APIUsageStats, TranscriptionStats, SearchTrendsResponse, UserActivityData, LogFile, LogFilesResponse, LogContentResponse
router = APIRouter(prefix='/admin')

class UserListResponse(BaseModel):
    total_count: int
    users: List[Dict[str, Any]]

class UserUpdateRequest(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None

class UserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: Optional[str] = None
    role: str
    status: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: Optional[str] = None
    role: str = 'user'
    status: str = 'active'

class UpdateCreditRequestStatusRequest(BaseModel):
    action: str = Field(..., description="Action to take: 'approve' or 'reject'")
    credits_to_add: Optional[int] = Field(None, description='Credits to add (required for approval)')

    class Config:
        schema_extra = {'example': {'action': 'approve', 'credits_to_add': 100}}

@router.get('/gemini-keys/status', status_code=status.HTTP_200_OK)
async def get_gemini_keys_status(current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Return current Gemini keys usage and health as tracked by the GeminiKeyManager.
    Includes per-key cooldowns, RPM/RPS/TPM windows, daily counters, and error counts.
    """
    try:
        status_obj = gemini_key_manager.get_status()
        return status_obj
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Failed to retrieve Gemini keys status: {str(e)}')

class IPCreditResponse(BaseModel):
    id: str
    ip: str
    credits: int
    created: datetime
    last_used: datetime

class IPCreditListResponse(BaseModel):
    total_count: int
    ip_credits: List[IPCreditResponse]

class UpdateCreditsRequest(BaseModel):
    credits: int = Field(..., ge=0, description='New credit amount (must be non-negative)')
    reason: Optional[str] = Field(None, max_length=500, description='Reason for credit adjustment')

class UpdateCreditsResponse(BaseModel):
    id: str
    ip: str
    old_credits: int
    new_credits: int
    updated_at: datetime
    updated_by: str

def sanitize_user(user: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive data and format the user object for API responses"""
    if not user:
        return {}
    user['id'] = str(user.pop('_id')) if '_id' in user else None
    user.pop('password', None)
    return user

@router.get('/ip-credits', response_model=IPCreditListResponse, status_code=status.HTTP_200_OK)
async def list_ip_credits(current_user: Dict[str, Any]=Depends(requires_role('admin')), page: int=Query(1, ge=1, description='Page number, starting from 1'), limit: int=Query(10, ge=1, le=100, description='Number of items per page'), sort_by: str=Query('last_used', description='Field to sort by'), sort_order: int=Query(-1, description='Sort order: 1 for ascending, -1 for descending'), ip: Optional[str]=Query(None, description='Filter by specific IP address'), min_credits: Optional[int]=Query(None, description='Filter by minimum credits'), max_credits: Optional[int]=Query(None, description='Filter by maximum credits'), search: Optional[str]=Query(None, description='Search in IP address')):
    """
    List all IP credits with pagination and filtering.
    Only accessible to administrators.
    """
    filter_query = {}
    if ip:
        filter_query['ip'] = ip
    if min_credits is not None:
        filter_query.setdefault('credits', {})['$gte'] = min_credits
    if max_credits is not None:
        filter_query.setdefault('credits', {})['$lte'] = max_credits
    if search:
        filter_query['ip'] = {'$regex': search, '$options': 'i'}
    total_count = await ip_credits_collection.count_documents(filter_query)
    skip = (page - 1) * limit
    cursor = ip_credits_collection.find(filter_query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)
    ip_credits = await cursor.to_list(length=limit)
    sanitized_ip_credits = []
    for ip_credit in ip_credits:
        sanitized_ip_credits.append(IPCreditResponse(id=str(ip_credit['_id']), ip=ip_credit['ip'], credits=ip_credit['credits'], created=datetime.fromtimestamp(ip_credit['created']), last_used=datetime.fromtimestamp(ip_credit['last_used'])))
    return IPCreditListResponse(total_count=total_count, ip_credits=sanitized_ip_credits)

@router.get('/ip-credits/{ip_address}', response_model=IPCreditResponse, status_code=status.HTTP_200_OK)
async def get_ip_credits(ip_address: str, current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Get credits for a specific IP address.
    Only accessible to administrators.
    """
    ip_credit = await ip_credits_collection.find_one({'ip': ip_address})
    if not ip_credit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='IP address not found')
    return IPCreditResponse(id=str(ip_credit['_id']), ip=ip_credit['ip'], credits=ip_credit['credits'], created=datetime.fromtimestamp(ip_credit['created']), last_used=datetime.fromtimestamp(ip_credit['last_used']))

@router.put('/ip-credits/{ip_address}/credits', response_model=UpdateCreditsResponse, status_code=status.HTTP_200_OK)
async def update_ip_credits(ip_address: str, request: UpdateCreditsRequest, current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Update credits for a specific IP address.
    Only accessible to administrators.
    """
    ip_credit = await ip_credits_collection.find_one({'ip': ip_address})
    if not ip_credit:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'IP address {ip_address} not found in credits system')
    old_credits = ip_credit['credits']
    current_timestamp = int(time.time())
    update_data = {'credits': request.credits, 'last_updated': current_timestamp, 'updated_by': current_user.get('email', current_user.get('id', 'unknown'))}
    result = await ip_credits_collection.update_one({'ip': ip_address}, {'$set': update_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail='Failed to update credits')
    return UpdateCreditsResponse(id=str(ip_credit['_id']), ip=ip_address, old_credits=old_credits, new_credits=request.credits, updated_at=datetime.fromtimestamp(current_timestamp), updated_by=current_user.get('email', current_user.get('id', 'unknown')))

@router.get('/users', response_model=UserListResponse, status_code=status.HTTP_200_OK)
async def list_users(current_user: Dict[str, Any]=Depends(requires_role('admin')), page: int=Query(1, ge=1, description='Page number, starting from 1'), limit: int=Query(10, ge=1, le=100, description='Number of items per page'), sort_by: str=Query('created_at', description='Field to sort by'), sort_order: int=Query(-1, description='Sort order: 1 for ascending, -1 for descending'), role: Optional[str]=Query(None, description='Filter by user role'), status: Optional[str]=Query(None, description='Filter by user status'), search: Optional[str]=Query(None, description='Search in email and full_name')):
    """
    List all users with pagination and filtering.
    Only accessible to administrators.
    """
    filter_query = {}
    if role:
        filter_query['role'] = role
    if status:
        filter_query['status'] = status
    if search:
        filter_query['$or'] = [{'email': {'$regex': search, '$options': 'i'}}, {'full_name': {'$regex': search, '$options': 'i'}}]
    total_count = await users_collection.count_documents(filter_query)
    skip = (page - 1) * limit
    cursor = users_collection.find(filter_query)
    cursor = cursor.sort(sort_by, sort_order)
    cursor = cursor.skip(skip).limit(limit)
    users = await cursor.to_list(length=limit)
    sanitized_users = [sanitize_user(user) for user in users]
    return UserListResponse(total_count=total_count, users=sanitized_users)

@router.get('/users/{user_id}', response_model=UserResponse, status_code=status.HTTP_200_OK)
async def get_user_details(user_id: str=Path(..., description='User ID'), current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Get detailed information about a specific user.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid user ID format')
    user = await users_collection.find_one({'_id': obj_id})
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'User with ID {user_id} not found')
    return sanitize_user(user)

@router.put('/users/{user_id}', response_model=UserResponse, status_code=status.HTTP_200_OK)
async def update_user(update_data: UserUpdateRequest, user_id: str=Path(..., description='User ID'), current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Update user details (role, status, etc.).
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid user ID format')
    existing_user = await users_collection.find_one({'_id': obj_id})
    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'User with ID {user_id} not found')
    update_dict = update_data.dict(exclude_unset=True, exclude_none=True)
    if not update_dict:
        return sanitize_user(existing_user)
    update_dict['updated_at'] = datetime.utcnow()
    await users_collection.update_one({'_id': obj_id}, {'$set': update_dict})
    updated_user = await users_collection.find_one({'_id': obj_id})
    return sanitize_user(updated_user)

@router.delete('/users/{user_id}', status_code=status.HTTP_200_OK)
async def delete_user(user_id: str=Path(..., description='User ID'), current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Permanently delete a user from the system.
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid user ID format')
    existing_user = await users_collection.find_one({'_id': obj_id})
    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'User with ID {user_id} not found')
    if str(existing_user['_id']) == str(current_user['_id']):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot delete your own account')
    await users_collection.delete_one({'_id': obj_id})
    return {'status': 'success', 'detail': f'User {user_id} has been permanently deleted'}

@router.patch('/users/{user_id}/status', status_code=status.HTTP_200_OK)
async def update_user_status(user_id: str=Path(..., description='User ID'), status_update: Dict[str, str]=Body(..., example={'status': 'inactive'}), current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Update a user's status (activate/deactivate/suspend).
    Only accessible to administrators.
    """
    try:
        obj_id = ObjectId(user_id)
    except:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid user ID format')
    existing_user = await users_collection.find_one({'_id': obj_id})
    if not existing_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'User with ID {user_id} not found')
    new_status = status_update.get('status')
    if not new_status or new_status not in ['active', 'inactive', 'suspended']:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Valid status required: 'active', 'inactive', or 'suspended'")
    if str(existing_user['_id']) == str(current_user['_id']):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Cannot change the status of your own account')
    await users_collection.update_one({'_id': obj_id}, {'$set': {'status': new_status, 'updated_at': datetime.utcnow()}})
    status_message = 'activated' if new_status == 'active' else new_status
    return {'status': 'success', 'detail': f'User {user_id} has been {status_message}'}

@router.post('/users/create', response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(user_data: UserCreateRequest, current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Create a new user directly from the admin panel.
    Only accessible to administrators.
    """
    existing_user = await get_user_by_email(user_data.email)
    if existing_user:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f'User with email {user_data.email} already exists')
    valid_roles = ['user', 'premium', 'admin']
    if user_data.role not in valid_roles:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}")
    valid_statuses = ['active', 'inactive', 'suspended']
    if user_data.status not in valid_statuses:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid status. Must be one of: {', '.join(valid_statuses)}")
    hashed_password = get_password_hash(user_data.password)
    new_user = {'email': user_data.email, 'password': hashed_password, 'full_name': user_data.full_name, 'role': user_data.role, 'status': user_data.status, 'created_at': datetime.utcnow(), 'updated_at': datetime.utcnow(), 'created_by': str(current_user['_id'])}
    result = await users_collection.insert_one(new_user)
    created_user = await users_collection.find_one({'_id': result.inserted_id})
    return sanitize_user(created_user)

@router.get('/analytics/usage', response_model=APIUsageStats, status_code=status.HTTP_200_OK)
async def get_api_usage_metrics(current_user: Dict[str, Any]=Depends(requires_role('admin')), days: int=Query(30, ge=1, le=365, description='Number of days to include in analytics'), ip_address: Optional[str]=Query(None, description='Filter by specific IP address'), user_id: Optional[str]=Query(None, description='Filter by specific user ID'), endpoint: Optional[str]=Query(None, description='Filter by specific endpoint'), status_code: Optional[int]=Query(None, description='Filter by HTTP status code'), start_date: Optional[datetime]=Query(None, description='Custom start date'), end_date: Optional[datetime]=Query(None, description='Custom end date')):
    """
    Track API usage metrics with advanced filtering.
    Returns data on API usage patterns, endpoint popularity, and performance metrics.
    Only accessible to administrators.
    """
    if start_date and end_date:
        filter_start = start_date
        filter_end = end_date
    else:
        filter_start = datetime.utcnow() - timedelta(days=days)
        filter_end = datetime.utcnow()
    match_filter = {'timestamp': {'$gte': filter_start, '$lte': filter_end}}
    if ip_address:
        match_filter['ip_address'] = ip_address
    if user_id:
        match_filter['user_id'] = user_id
    if endpoint:
        match_filter['endpoint'] = {'$regex': endpoint, '$options': 'i'}
    if status_code:
        match_filter['status_code'] = status_code
    pipeline = [{'$match': match_filter}, {'$group': {'_id': None, 'total_requests': {'$sum': 1}, 'average_response_time': {'$avg': '$response_time'}, 'min_response_time': {'$min': '$response_time'}, 'max_response_time': {'$max': '$response_time'}, 'min_date': {'$min': '$timestamp'}, 'max_date': {'$max': '$timestamp'}}}]
    result = await api_usage_collection.aggregate(pipeline).to_list(length=1)
    if not result:
        return APIUsageStats(date_range={'start': filter_start, 'end': filter_end})
    endpoint_pipeline = [{'$match': match_filter}, {'$group': {'_id': '$endpoint', 'count': {'$sum': 1}, 'avg_response_time': {'$avg': '$response_time'}, 'success_rate': {'$avg': {'$cond': [{'$lt': ['$status_code', 400]}, 1, 0]}}}}, {'$sort': {'count': -1}}]
    endpoint_results = await api_usage_collection.aggregate(endpoint_pipeline).to_list(length=100)
    endpoint_counts = {item['_id']: item['count'] for item in endpoint_results}
    endpoint_details = [{'endpoint': item.get('_id'), 'count': item.get('count', 0), 'avg_response_time': item.get('avg_response_time'), 'success_rate': item.get('success_rate')} for item in endpoint_results]
    ip_pipeline = [{'$match': dict(match_filter, **{'ip_address': {'$exists': True, '$nin': [None, '']}})}, {'$group': {'_id': '$ip_address', 'count': {'$sum': 1}, 'unique_endpoints': {'$addToSet': '$endpoint'}, 'avg_response_time': {'$avg': '$response_time'}, 'last_seen': {'$max': '$timestamp'}, 'first_seen': {'$min': '$timestamp'}, 'user_agents': {'$addToSet': '$user_agent'}}}, {'$sort': {'count': -1}}, {'$limit': 100}]
    ip_results = await api_usage_collection.aggregate(ip_pipeline).to_list(length=100)
    ip_counts = {str(item['_id']): item['count'] for item in ip_results}
    ip_details = [{'ip': str(item.get('_id')), 'count': item.get('count', 0), 'avg_response_time': item.get('avg_response_time'), 'last_seen': item.get('last_seen'), 'first_seen': item.get('first_seen'), 'unique_endpoints': len(item.get('unique_endpoints', []))} for item in ip_results]
    user_pipeline = [{'$match': dict(match_filter, **{'user_id': {'$exists': True, '$nin': [None, '']}})}, {'$group': {'_id': '$user_id', 'count': {'$sum': 1}, 'unique_endpoints': {'$addToSet': '$endpoint'}, 'avg_response_time': {'$avg': '$response_time'}, 'last_activity': {'$max': '$timestamp'}}}, {'$sort': {'count': -1}}, {'$limit': 50}]
    user_results = await api_usage_collection.aggregate(user_pipeline).to_list(length=50)
    user_counts = {str(item['_id']): item['count'] for item in user_results}
    status_pipeline = [{'$match': match_filter}, {'$group': {'_id': '$status_code', 'count': {'$sum': 1}}}, {'$sort': {'_id': 1}}]
    status_results = await api_usage_collection.aggregate(status_pipeline).to_list(length=20)
    status_counts = {str(item['_id']): item['count'] for item in status_results}
    hourly_pipeline = [{'$match': match_filter}, {'$group': {'_id': {'$hour': '$timestamp'}, 'count': {'$sum': 1}}}, {'$sort': {'_id': 1}}]
    hourly_results = await api_usage_collection.aggregate(hourly_pipeline).to_list(length=24)
    hourly_counts = {str(item['_id']): item['count'] for item in hourly_results}
    stats = APIUsageStats(total_requests=result[0].get('total_requests', 0), endpoint_counts=endpoint_counts, user_counts=user_counts, ip_counts=ip_counts, status_counts=status_counts, hourly_distribution=hourly_counts, average_response_time=result[0].get('average_response_time'), min_response_time=result[0].get('min_response_time'), max_response_time=result[0].get('max_response_time'), endpoint_details=endpoint_details, ip_details=ip_details, date_range={'start': result[0].get('min_date', filter_start), 'end': result[0].get('max_date', filter_end)})
    return stats

@router.get('/vector-space', status_code=status.HTTP_200_OK)
async def get_vector_space(current_user: Dict[str, Any]=Depends(requires_role('admin')), top_k: int=Query(1000, ge=10, le=5000, description='Number of vectors to sample'), file_name_contains: Optional[str]=Query(None, description='Case-insensitive substring to filter by file_name metadata')):
    """
    Return PCA-reduced 3D coordinates and metadata for a sample of vectors in Pinecone.

    This endpoint issues a random vector query to Pinecone to retrieve a sample of vectors,
    then reduces their dimensionality to 3D using PCA for visualization.
    """
    try:
        if pinecone_index is None:
            ok = init_pinecone()
            if not ok:
                raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Pinecone is not initialized')
        from services.pinecone_service import index as _index, EMBEDDING_DIMENSION as _DIM
        if _index is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail='Pinecone index unavailable')
        dimension = int(os.getenv('EMBEDDING_DIMENSION', str(_DIM if _DIM else 768)))
        rng = np.random.default_rng()
        random_vec = rng.random(dimension, dtype=np.float32).tolist()
        try:
            response = _index.query(vector=random_vec, top_k=top_k, include_values=True, include_metadata=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f'Pinecone query failed: {str(e)}')
        matches = response.get('matches', []) if isinstance(response, dict) else getattr(response, 'matches', [])
        if not matches:
            return {'total': 0, 'dimension': dimension, 'reduced_dimension': 3, 'points': [], 'message': 'No vectors returned from Pinecone'}
        vectors = []
        metas = []
        ids = []
        for m in matches:
            vals = m.get('values') if isinstance(m, dict) else getattr(m, 'values', None)
            meta = m.get('metadata') if isinstance(m, dict) else getattr(m, 'metadata', None)
            mid = m.get('id') if isinstance(m, dict) else getattr(m, 'id', None)
            if vals is not None:
                vectors.append(vals)
                metas.append(meta or {})
                ids.append(mid)
        if not vectors:
            return {'total': 0, 'dimension': dimension, 'reduced_dimension': 3, 'points': [], 'message': 'No vector values included in response'}
        if file_name_contains:
            q = str(file_name_contains).lower()
            filtered = [(v, m, i) for v, m, i in zip(vectors, metas, ids) if str((m or {}).get('file_name', '')).lower().find(q) != -1]
            if filtered:
                vectors, metas, ids = zip(*filtered)
                vectors, metas, ids = (list(vectors), list(metas), list(ids))
            else:
                return {'total': 0, 'dimension': dimension, 'reduced_dimension': 3, 'points': [], 'message': 'No vectors matched file_name filter'}
        X = np.array(vectors, dtype=np.float32)
        n_samples, n_features = X.shape
        reduced = None
        if n_samples >= 3 and n_features >= 3:
            try:
                pca = PCA(n_components=3)
                reduced = pca.fit_transform(X)
            except Exception:
                pad_width = max(0, 3 - n_features)
                X_pad = np.pad(X[:, :min(3, n_features)], ((0, 0), (0, pad_width)))
                reduced = X_pad[:, :3]
        else:
            pad_width = max(0, 3 - n_features)
            X_pad = np.pad(X[:, :min(3, n_features)], ((0, 0), (0, pad_width)))
            reduced = X_pad[:, :3]
        points = []
        for i in range(len(metas)):
            m = metas[i] or {}
            x, y, z = (float(reduced[i, 0]), float(reduced[i, 1]), float(reduced[i, 2]))
            points.append({'id': ids[i], 'x': x, 'y': y, 'z': z, 'file_name': m.get('file_name'), 'chunk_index': m.get('chunk_index'), 'total_chunks': m.get('total_chunks'), 'start_time': m.get('start_time'), 'end_time': m.get('end_time'), 'text': m.get('text')})
        return {'total': len(points), 'dimension': dimension, 'reduced_dimension': 3, 'points': points}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f'Failed to build vector space: {str(e)}')

@router.get('/analytics/ip-details/{ip_address}', status_code=status.HTTP_200_OK)
async def get_ip_detailed_analytics(ip_address: str, current_user: Dict[str, Any]=Depends(requires_role('admin')), days: int=Query(30, ge=1, le=365, description='Number of days to include in analytics')):
    """
    Get detailed analytics for a specific IP address.
    Returns comprehensive usage patterns, endpoints accessed, and behavior analysis.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    match_filter = {'timestamp': {'$gte': start_date}, 'ip_address': ip_address}
    overall_pipeline = [{'$match': match_filter}, {'$group': {'_id': None, 'total_requests': {'$sum': 1}, 'unique_endpoints': {'$addToSet': '$endpoint'}, 'unique_user_agents': {'$addToSet': '$user_agent'}, 'avg_response_time': {'$avg': '$response_time'}, 'first_seen': {'$min': '$timestamp'}, 'last_seen': {'$max': '$timestamp'}, 'unique_users': {'$addToSet': '$user_id'}}}]
    overall_result = await api_usage_collection.aggregate(overall_pipeline).to_list(length=1)
    endpoint_pipeline = [{'$match': match_filter}, {'$group': {'_id': '$endpoint', 'count': {'$sum': 1}, 'avg_response_time': {'$avg': '$response_time'}, 'status_codes': {'$push': '$status_code'}, 'last_accessed': {'$max': '$timestamp'}}}, {'$sort': {'count': -1}}]
    endpoint_results = await api_usage_collection.aggregate(endpoint_pipeline).to_list(length=100)
    hourly_pipeline = [{'$match': match_filter}, {'$group': {'_id': {'$hour': '$timestamp'}, 'count': {'$sum': 1}}}, {'$sort': {'_id': 1}}]
    hourly_results = await api_usage_collection.aggregate(hourly_pipeline).to_list(length=24)
    daily_pipeline = [{'$match': match_filter}, {'$group': {'_id': {'year': {'$year': '$timestamp'}, 'month': {'$month': '$timestamp'}, 'day': {'$dayOfMonth': '$timestamp'}}, 'count': {'$sum': 1}, 'avg_response_time': {'$avg': '$response_time'}}}, {'$sort': {'_id': 1}}]
    daily_results = await api_usage_collection.aggregate(daily_pipeline).to_list(length=365)
    status_pipeline = [{'$match': match_filter}, {'$group': {'_id': '$status_code', 'count': {'$sum': 1}}}, {'$sort': {'_id': 1}}]
    status_results = await api_usage_collection.aggregate(status_pipeline).to_list(length=20)
    if not overall_result:
        return {'ip_address': ip_address, 'message': 'No data found for this IP address in the specified time range', 'date_range': {'start': start_date, 'end': datetime.utcnow()}}
    overall_stats = overall_result[0]
    return {'ip_address': ip_address, 'summary': {'total_requests': overall_stats.get('total_requests', 0), 'unique_endpoints': len(overall_stats.get('unique_endpoints', [])), 'unique_user_agents': len(overall_stats.get('unique_user_agents', [])), 'unique_users': len([u for u in overall_stats.get('unique_users', []) if u]), 'avg_response_time': overall_stats.get('avg_response_time'), 'first_seen': overall_stats.get('first_seen'), 'last_seen': overall_stats.get('last_seen')}, 'endpoints': [{'endpoint': result['_id'], 'count': result['count'], 'avg_response_time': result['avg_response_time'], 'last_accessed': result['last_accessed'], 'success_rate': len([s for s in result['status_codes'] if s < 400]) / len(result['status_codes']) if result['status_codes'] else 0} for result in endpoint_results], 'hourly_pattern': {str(result['_id']): result['count'] for result in hourly_results}, 'daily_activity': [{'date': f"{result['_id']['year']}-{result['_id']['month']:02d}-{result['_id']['day']:02d}", 'requests': result['count'], 'avg_response_time': result['avg_response_time']} for result in daily_results], 'status_distribution': {str(result['_id']): result['count'] for result in status_results}, 'user_agents': overall_stats.get('unique_user_agents', []), 'date_range': {'start': start_date, 'end': datetime.utcnow()}}

@router.get('/analytics/real-time', status_code=status.HTTP_200_OK)
async def get_real_time_analytics(current_user: Dict[str, Any]=Depends(requires_role('admin')), minutes: int=Query(60, ge=1, le=1440, description='Number of minutes for real-time data')):
    """
    Get real-time analytics for the last N minutes.
    Returns live data on current API usage, active IPs, and performance metrics.
    Only accessible to administrators.
    """
    start_time = datetime.utcnow() - timedelta(minutes=minutes)
    match_filter = {'timestamp': {'$gte': start_time}}
    summary_pipeline = [{'$match': match_filter}, {'$group': {'_id': None, 'total_requests': {'$sum': 1}, 'unique_ips': {'$addToSet': '$ip_address'}, 'unique_users': {'$addToSet': '$user_id'}, 'avg_response_time': {'$avg': '$response_time'}, 'error_count': {'$sum': {'$cond': [{'$gte': ['$status_code', 400]}, 1, 0]}}}}]
    summary_result = await api_usage_collection.aggregate(summary_pipeline).to_list(length=1)
    minute_pipeline = [{'$match': match_filter}, {'$group': {'_id': {'year': {'$year': '$timestamp'}, 'month': {'$month': '$timestamp'}, 'day': {'$dayOfMonth': '$timestamp'}, 'hour': {'$hour': '$timestamp'}, 'minute': {'$minute': '$timestamp'}}, 'count': {'$sum': 1}, 'avg_response_time': {'$avg': '$response_time'}, 'errors': {'$sum': {'$cond': [{'$gte': ['$status_code', 400]}, 1, 0]}}}}, {'$sort': {'_id': 1}}]
    minute_results = await api_usage_collection.aggregate(minute_pipeline).to_list(length=1440)
    active_ips_pipeline = [{'$match': match_filter}, {'$group': {'_id': '$ip_address', 'count': {'$sum': 1}, 'last_seen': {'$max': '$timestamp'}, 'endpoints': {'$addToSet': '$endpoint'}}}, {'$sort': {'count': -1}}, {'$limit': 20}]
    active_ips_results = await api_usage_collection.aggregate(active_ips_pipeline).to_list(length=20)
    endpoints_pipeline = [{'$match': match_filter}, {'$group': {'_id': '$endpoint', 'count': {'$sum': 1}, 'avg_response_time': {'$avg': '$response_time'}}}, {'$sort': {'count': -1}}, {'$limit': 15}]
    endpoints_results = await api_usage_collection.aggregate(endpoints_pipeline).to_list(length=15)
    if not summary_result:
        return {'message': 'No real-time data available', 'time_range': {'start': start_time, 'end': datetime.utcnow()}}
    summary = summary_result[0]
    return {'summary': {'total_requests': summary.get('total_requests', 0), 'unique_ips': len(summary.get('unique_ips', [])), 'unique_users': len([u for u in summary.get('unique_users', []) if u]), 'avg_response_time': summary.get('avg_response_time'), 'error_rate': summary.get('error_count', 0) / summary.get('total_requests', 1) * 100, 'requests_per_minute': summary.get('total_requests', 0) / minutes}, 'timeline': [{'timestamp': f"{result['_id']['year']}-{result['_id']['month']:02d}-{result['_id']['day']:02d} {result['_id']['hour']:02d}:{result['_id']['minute']:02d}", 'requests': result['count'], 'avg_response_time': result['avg_response_time'], 'errors': result['errors']} for result in minute_results], 'active_ips': [{'ip': result['_id'], 'requests': result['count'], 'last_seen': result['last_seen'], 'unique_endpoints': len(result['endpoints'])} for result in active_ips_results], 'top_endpoints': [{'endpoint': result['_id'], 'requests': result['count'], 'avg_response_time': result['avg_response_time']} for result in endpoints_results], 'time_range': {'start': start_time, 'end': datetime.utcnow()}}


@router.get('/analytics/ip-geo-summary', status_code=status.HTTP_200_OK)
async def get_ip_geo_summary(current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Aggregate unique IP hits by country and state/region for usage map visualization.
    Returns a list of { country_code, country, state, count } sorted by count desc.
    """
    pipeline = [
        { '$match': { 'country_code': { '$exists': True, '$nin': [None, ''] } } },
        { '$group': { '_id': { 'cc': '$country_code', 'name': '$country', 'state': '$state' }, 'count': { '$sum': 1 } } },
        { '$project': { '_id': 0, 'country_code': '$_id.cc', 'country': '$_id.name', 'state': '$_id.state', 'count': 1 } },
        { '$sort': { 'count': -1 } },
    ]
    results = await ip_hits_collection.aggregate(pipeline).to_list(length=500)
    return { 'items': results }


@router.get('/analytics/transcriptions', response_model=TranscriptionStats, status_code=status.HTTP_200_OK)
async def get_transcription_statistics(current_user: Dict[str, Any]=Depends(requires_role('admin')), days: int=Query(30, ge=1, le=365, description='Number of days to include in statistics')):
    """
    Monitor transcription statistics.
    Returns data on transcription success rates, durations, and language distributions.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    pipeline = [{'$match': {'timestamp': {'$gte': start_date}}}, {'$group': {'_id': None, 'total_transcriptions': {'$sum': 1}, 'successful_transcriptions': {'$sum': {'$cond': [{'$eq': ['$status', 'success']}, 1, 0]}}, 'failed_transcriptions': {'$sum': {'$cond': [{'$eq': ['$status', 'error']}, 1, 0]}}, 'average_duration': {'$avg': '$processing_time'}, 'total_audio_length': {'$sum': '$audio_length'}, 'min_date': {'$min': '$timestamp'}, 'max_date': {'$max': '$timestamp'}}}]
    result = await transcription_stats_collection.aggregate(pipeline).to_list(length=1)
    if not result:
        return TranscriptionStats(date_range={'start': start_date, 'end': datetime.utcnow()})
    language_pipeline = [{'$match': {'timestamp': {'$gte': start_date}, 'language': {'$exists': True}}}, {'$group': {'_id': '$language', 'count': {'$sum': 1}}}, {'$sort': {'count': -1}}]
    language_results = await transcription_stats_collection.aggregate(language_pipeline).to_list(length=50)
    language_counts = {item['_id']: item['count'] for item in language_results}
    stats = TranscriptionStats(total_transcriptions=result[0].get('total_transcriptions', 0), successful_transcriptions=result[0].get('successful_transcriptions', 0), failed_transcriptions=result[0].get('failed_transcriptions', 0), average_duration=result[0].get('average_duration'), total_audio_length=result[0].get('total_audio_length'), languages=language_counts, date_range={'start': result[0].get('min_date', start_date), 'end': result[0].get('max_date', datetime.utcnow())})
    return stats

@router.get('/analytics/search-trends', response_model=SearchTrendsResponse, status_code=status.HTTP_200_OK)
async def get_search_trends(current_user: Dict[str, Any]=Depends(requires_role('admin')), days: int=Query(30, ge=1, le=365, description='Number of days to include in trends'), limit: int=Query(20, ge=5, le=100, description='Number of top search terms to return')):
    """
    Track popular search terms.
    Returns data on trending search terms and patterns.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    pipeline = [{'$match': {'timestamp': {'$gte': start_date}}}, {'$group': {'_id': '$term', 'count': {'$sum': 1}, 'last_searched': {'$max': '$timestamp'}}}, {'$sort': {'count': -1}}, {'$limit': limit}]
    results = await search_trends_collection.aggregate(pipeline).to_list(length=limit)
    metrics_pipeline = [{'$match': {'timestamp': {'$gte': start_date}}}, {'$group': {'_id': None, 'total_searches': {'$sum': 1}, 'min_date': {'$min': '$timestamp'}, 'max_date': {'$max': '$timestamp'}}}]
    metrics = await search_trends_collection.aggregate(metrics_pipeline).to_list(length=1)
    unique_terms_pipeline = [{'$match': {'timestamp': {'$gte': start_date}}}, {'$group': {'_id': '$term'}}, {'$count': 'unique_terms'}]
    unique_terms_result = await search_trends_collection.aggregate(unique_terms_pipeline).to_list(length=1)
    top_terms = []
    for result in results:
        top_terms.append({'term': result['_id'], 'count': result['count'], 'last_searched': result['last_searched']})
    response = {'top_terms': top_terms, 'total_searches': metrics[0]['total_searches'] if metrics else 0, 'unique_terms': unique_terms_result[0]['unique_terms'] if unique_terms_result else 0, 'date_range': {'start': metrics[0]['min_date'] if metrics else start_date, 'end': metrics[0]['max_date'] if metrics else datetime.utcnow()}}
    return response

@router.get('/analytics/user-activity', response_model=UserActivityData, status_code=status.HTTP_200_OK)
async def get_user_activity(current_user: Dict[str, Any]=Depends(requires_role('admin')), days: int=Query(30, ge=1, le=365, description='Number of days to include in activity data')):
    """
    Monitor user engagement.
    Returns data on user activity, session metrics, and feature usage.
    Only accessible to administrators.
    """
    start_date = datetime.utcnow() - timedelta(days=days)
    pipeline = [{'$match': {'timestamp': {'$gte': start_date}}}, {'$group': {'_id': None, 'total_active_users': {'$addToSet': '$user_id'}, 'average_session_duration': {'$avg': '$session_duration'}, 'min_date': {'$min': '$timestamp'}, 'max_date': {'$max': '$timestamp'}}}]
    result = await user_activity_collection.aggregate(pipeline).to_list(length=1)
    new_users_pipeline = [{'$match': {'created_at': {'$gte': start_date}}}, {'$count': 'new_users'}]
    new_users_result = await users_collection.aggregate(new_users_pipeline).to_list(length=1)
    hours_pipeline = [{'$match': {'timestamp': {'$gte': start_date}}}, {'$project': {'hour': {'$hour': '$timestamp'}}}, {'$group': {'_id': '$hour', 'count': {'$sum': 1}}}, {'$sort': {'_id': 1}}]
    hours_result = await user_activity_collection.aggregate(hours_pipeline).to_list(length=24)
    hours_distribution = {item['_id']: item['count'] for item in hours_result}
    features_pipeline = [{'$match': {'timestamp': {'$gte': start_date}, 'feature': {'$exists': True}}}, {'$group': {'_id': '$feature', 'count': {'$sum': 1}}}, {'$sort': {'count': -1}}, {'$limit': 10}]
    features_result = await user_activity_collection.aggregate(features_pipeline).to_list(length=10)
    features_distribution = {item['_id']: item['count'] for item in features_result}
    stats = UserActivityData(total_active_users=len(result[0]['total_active_users']) if result and 'total_active_users' in result[0] else 0, new_users=new_users_result[0]['new_users'] if new_users_result else 0, returning_users=len(result[0]['total_active_users']) - (new_users_result[0]['new_users'] if new_users_result else 0) if result and 'total_active_users' in result[0] else 0, average_session_duration=result[0].get('average_session_duration') if result else None, most_active_hours=hours_distribution, most_used_features=features_distribution, date_range={'start': result[0].get('min_date', start_date) if result else start_date, 'end': result[0].get('max_date', datetime.utcnow()) if result else datetime.utcnow()})
    return stats

@router.get('/log-files', response_model=LogFilesResponse, status_code=status.HTTP_200_OK)
async def list_log_files(current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    List all log files in the logs directory, sorted by date (newest first).
    Only accessible to administrators.
    """
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    if not os.path.exists(logs_dir):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Logs directory not found')
    log_files = []
    try:
        for filename in os.listdir(logs_dir):
            if filename.endswith('.log'):
                file_path = os.path.join(logs_dir, filename)
                file_stat = os.stat(file_path)
                date_part = filename.replace('.log', '')
                log_file = LogFile(filename=filename, size=file_stat.st_size, last_modified=datetime.fromtimestamp(file_stat.st_mtime), date=date_part)
                log_files.append(log_file)
        log_files.sort(key=lambda x: x.date, reverse=True)
        return LogFilesResponse(log_files=log_files, total_count=len(log_files))
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Error reading logs directory: {str(e)}')

@router.get('/log-files/{filename}', response_model=LogContentResponse, status_code=status.HTTP_200_OK)
async def get_log_file_content(filename: str=Path(..., description='Name of the log file to read'), current_user: Dict[str, Any]=Depends(requires_role('admin')), lines: Optional[int]=Query(None, ge=1, le=10000, description='Number of lines to read from the end of file'), search: Optional[str]=Query(None, description='Search for specific text in the log file')):
    """
    Read the contents of a specific log file.
    Optionally filter by number of lines or search for specific text.
    Only accessible to administrators.
    """
    logs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')
    file_path = os.path.join(logs_dir, filename)
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid filename')
    if not os.path.exists(file_path):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Log file '{filename}' not found")
    try:
        file_stat = os.stat(file_path)
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            if lines:
                all_lines = f.readlines()
                content_lines = all_lines[-lines:] if len(all_lines) > lines else all_lines
                content = ''.join(content_lines)
                total_lines = len(all_lines)
            else:
                content = f.read()
                total_lines = len(content.splitlines())
            if search:
                filtered_lines = []
                for line in content.splitlines():
                    if search.lower() in line.lower():
                        filtered_lines.append(line)
                content = '\n'.join(filtered_lines)
        return LogContentResponse(filename=filename, content=content, size=file_stat.st_size, last_modified=datetime.fromtimestamp(file_stat.st_mtime), total_lines=total_lines)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Error reading log file: {str(e)}')

@router.delete('/cleanup/audio-uploads', status_code=status.HTTP_200_OK)
async def cleanup_audio_uploads(current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Delete all files and subdirectories inside the audio uploads folder.
    Folder path: Backend/audio_uploads
    Only accessible to administrators.
    """
    base_dir = os.path.dirname(os.path.dirname(__file__))
    upload_dir = os.path.join(base_dir, 'audio_uploads')
    if not os.path.isdir(upload_dir):
        return {'status': 'success', 'detail': 'audio_uploads directory does not exist', 'deleted_files': 0, 'deleted_dirs': 0, 'deleted_bytes': 0, 'errors': []}

    def _cleanup_sync():
        deleted_files = 0
        deleted_dirs = 0
        deleted_bytes = 0
        errors: List[Dict[str, Any]] = []
        try:
            with os.scandir(upload_dir) as it:
                for entry in it:
                    path = entry.path
                    try:
                        if entry.is_file() or entry.is_symlink():
                            try:
                                deleted_bytes += os.path.getsize(path)
                            except Exception:
                                pass
                            os.remove(path)
                            deleted_files += 1
                        elif entry.is_dir():
                            for root, _, files in os.walk(path):
                                for fname in files:
                                    fpath = os.path.join(root, fname)
                                    try:
                                        deleted_bytes += os.path.getsize(fpath)
                                    except Exception:
                                        pass
                            shutil.rmtree(path)
                            deleted_dirs += 1
                    except Exception as e:
                        errors.append({'path': path, 'error': str(e)})
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f'Failed to scan directory: {str(e)}')
        return (deleted_files, deleted_dirs, deleted_bytes, errors)
    loop = asyncio.get_event_loop()
    deleted_files, deleted_dirs, deleted_bytes, errors = await loop.run_in_executor(None, _cleanup_sync)
    detail_msg = 'Cleanup completed'
    if errors:
        detail_msg += f' with {len(errors)} errors (likely locked files)'
    return {'status': 'success', 'detail': detail_msg, 'deleted_files': deleted_files, 'deleted_dirs': deleted_dirs, 'deleted_bytes': deleted_bytes, 'errors': errors}

@router.get('/credit-requests')
async def get_all_credit_requests(request: Request, current_user: Dict[str, Any]=Depends(requires_role('admin')), status_filter: Optional[str]=None, limit: int=50, skip: int=0):
    """
    Admin endpoint to view all credit requests.
    """
    try:
        query = {}
        if status_filter:
            query['status'] = status_filter
        else:
            query['status'] = 'pending'
        cursor = credit_requests_collection.find(query).sort('created_at', -1).skip(skip).limit(limit)
        requests = []
        async for request_doc in cursor:
            request_doc['_id'] = str(request_doc['_id'])
            request_doc['created_at'] = datetime.fromtimestamp(request_doc['created_at']).isoformat()
            if request_doc.get('updated_at'):
                request_doc['updated_at'] = datetime.fromtimestamp(request_doc['updated_at']).isoformat()
            requests.append(request_doc)
        return {'status': True, 'requests': requests, 'total': await credit_requests_collection.count_documents(query)}
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={'status': False, 'detail': f'An error occurred: {str(e)}'})

@router.put('/credit-requests/{request_id}/status')
async def update_credit_request_status(request_id: str, request: UpdateCreditRequestStatusRequest, current_user: Dict[str, Any]=Depends(requires_role('admin'))):
    """
    Admin endpoint to approve or reject credit requests.
    For approval, adds credits to the user's IP and updates request status.
    For rejection, only updates request status.
    """
    try:
        if not ObjectId.is_valid(request_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Invalid request ID format')
        credit_request = await credit_requests_collection.find_one({'_id': ObjectId(request_id)})
        if not credit_request:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail='Credit request not found')
        if credit_request['status'] != 'pending':
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Request is already {credit_request['status']}")
        current_timestamp = int(time.time())
        print('current_timestamp')
        print(current_timestamp)
        updated_by = current_user.get('email', current_user.get('id', 'unknown'))
        if request.action == 'approve':
            if not request.credits_to_add or request.credits_to_add < 1:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail='Credits to add must be greater than 0 for approval')
            ip_address = credit_request['ip_address']
            ip_credit = await ip_credits_collection.find_one({'ip': ip_address})
            if not ip_credit:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f'IP address {ip_address} not found in credits system')
            new_credits = ip_credit['credits'] + request.credits_to_add
            await ip_credits_collection.update_one({'ip': ip_address}, {'$set': {'credits': new_credits, 'last_updated': current_timestamp, 'updated_by': updated_by}})
            await credit_requests_collection.update_one({'_id': ObjectId(request_id)}, {'$set': {'status': 'approved', 'credits_added': request.credits_to_add, 'updated_at': current_timestamp, 'updated_by': updated_by}})
            return {'status': True, 'message': f'Credit request approved. Added {request.credits_to_add} credits to IP {ip_address}', 'credits_added': request.credits_to_add, 'new_total_credits': new_credits}
        elif request.action == 'reject':
            await credit_requests_collection.update_one({'_id': ObjectId(request_id)}, {'$set': {'status': 'rejected', 'updated_at': current_timestamp, 'updated_by': updated_by}})
            return {'status': True, 'message': 'Credit request rejected'}
        else:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid action. Must be 'approve' or 'reject'")
    except HTTPException:
        raise
    except Exception as e:
        return JSONResponse(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={'status': False, 'detail': f'An error occurred: {str(e)}'})