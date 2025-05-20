import requests
import json
from datetime import datetime, timedelta

class VoiceraAdminAPITester:
    def __init__(self, base_url, admin_token=None):
        self.base_url = base_url
        self.admin_token = admin_token
        self.headers = {
            "Content-Type": "application/json"
        }
        if self.admin_token:
            self.headers["Authorization"] = f"Bearer {self.admin_token}"
    
    def set_admin_token(self, token):
        self.admin_token = token
        self.headers["Authorization"] = f"Bearer {self.admin_token}"
    
    def print_response(self, response):
        print(f"\nStatus Code: {response.status_code}")
        try:
            print("Response:", json.dumps(response.json(), indent=2))
        except:
            print("Response:", response.text)
    
    def test_login(self):
        print("\n=== Testing Login ===")
        username = input("Enter admin username (default: rajdeep@mail.com): ") or "rajdeep@mail.com"
        password = input("Enter admin password (default: sample123): ") or "sample123"
        
        login_data = f"username={username}&password={password}"
        
        response = requests.post(
            f"{self.base_url}/api/auth/login",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data=login_data
        )
        
        self.print_response(response)
        
        if response.status_code == 200:
            token = response.json().get("access_token")
            self.set_admin_token(token)
            return token
        return None
    
    def test_list_users(self):
        print("\n=== Testing List Users ===")
        print("Options:")
        print("1. Basic list")
        print("2. With pagination")
        print("3. With filtering")
        choice = input("Enter your choice (1-3): ")
        
        url = f"{self.base_url}/api/admin/users"
        
        if choice == "2":
            page = input("Enter page number (default: 1): ") or "1"
            limit = input("Enter items per page (default: 10): ") or "10"
            url += f"?page={page}&limit={limit}"
        elif choice == "3":
            role = input("Filter by role (user/admin, leave empty to skip): ")
            status = input("Filter by status (active/inactive/suspended, leave empty to skip): ")
            search = input("Search term (leave empty to skip): ")
            sort_by = input("Sort by field (created_at, etc., leave empty to skip): ")
            sort_order = input("Sort order (1 for asc, -1 for desc, leave empty to skip): ")
            
            params = []
            if role: params.append(f"role={role}")
            if status: params.append(f"status={status}")
            if search: params.append(f"search={search}")
            if sort_by: params.append(f"sort_by={sort_by}")
            if sort_order: params.append(f"sort_order={sort_order}")
            
            if params:
                url += "?" + "&".join(params)
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
        return response.json().get('data', [])
    
    def test_get_user_details(self):
        print("\n=== Testing Get User Details ===")
        user_id = input("Enter user ID to fetch details: ")
        if not user_id:
            print("User ID is required")
            return None
        
        response = requests.get(
            f"{self.base_url}/api/admin/users/{user_id}",
            headers=self.headers
        )
        self.print_response(response)
        return response.json()
    
    def test_update_user(self):
        print("\n=== Testing Update User ===")
        user_id = input("Enter user ID to update: ")
        if not user_id:
            print("User ID is required")
            return
        
        print("Enter new values (leave empty to keep current):")
        email = input("Email: ")
        full_name = input("Full Name: ")
        role = input("Role (user/admin/premium): ")
        
        update_data = {}
        if email: update_data["email"] = email
        if full_name: update_data["full_name"] = full_name
        if role: update_data["role"] = role
        
        if not update_data:
            print("No fields to update")
            return
        
        response = requests.put(
            f"{self.base_url}/api/admin/users/{user_id}",
            headers=self.headers,
            json=update_data
        )
        self.print_response(response)
    
    def test_update_user_status(self):
        print("\n=== Testing Update User Status ===")
        user_id = input("Enter user ID to update status: ")
        if not user_id:
            print("User ID is required")
            return
        
        print("Status options: active, inactive, suspended")
        status = input("Enter new status: ")
        if status not in ["active", "inactive", "suspended"]:
            print("Invalid status")
            return
        
        response = requests.patch(
            f"{self.base_url}/api/admin/users/{user_id}/status",
            headers=self.headers,
            json={"status": status}
        )
        self.print_response(response)
    
    def test_create_user(self):
        print("\n=== Testing Create User ===")
        email = input("Email (required): ")
        if not email:
            print("Email is required")
            return
        
        password = input("Password (required): ")
        if not password:
            print("Password is required")
            return
        
        full_name = input("Full Name (required): ")
        if not full_name:
            print("Full Name is required")
            return
        
        role = input("Role (user/admin/premium, default: user): ") or "user"
        status = input("Status (active/inactive/suspended, default: active): ") or "active"
        
        user_data = {
            "email": email,
            "password": password,
            "full_name": full_name,
            "role": role,
            "status": status
        }
        
        response = requests.post(
            f"{self.base_url}/api/admin/users/create",
            headers=self.headers,
            json=user_data
        )
        self.print_response(response)
        return response.json()
    
    def test_delete_user(self):
        print("\n=== Testing Delete User ===")
        user_id = input("Enter user ID to delete: ")
        if not user_id:
            print("User ID is required")
            return
        
        response = requests.delete(
            f"{self.base_url}/api/admin/users/{user_id}",
            headers=self.headers
        )
        self.print_response(response)
    
    def test_analytics_usage(self):
        print("\n=== Testing Analytics Usage ===")
        days = input("Enter days to query (leave empty for default 30 days): ")
        url = f"{self.base_url}/api/admin/analytics/usage"
        if days:
            url += f"?days={days}"
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
    
    def test_analytics_transcriptions(self):
        print("\n=== Testing Transcription Analytics ===")
        days = input("Enter days to query (leave empty for default 30 days): ")
        url = f"{self.base_url}/api/admin/analytics/transcriptions"
        if days:
            url += f"?days={days}"
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
    
    def test_analytics_search_trends(self):
        print("\n=== Testing Search Trends ===")
        days = input("Enter days to query (leave empty for default 30 days): ")
        limit = input("Enter limit for results (leave empty for default 20): ")
        
        params = []
        if days: params.append(f"days={days}")
        if limit: params.append(f"limit={limit}")
        
        url = f"{self.base_url}/api/admin/analytics/search-trends"
        if params:
            url += "?" + "&".join(params)
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
    
    def test_analytics_user_activity(self):
        print("\n=== Testing User Activity ===")
        days = input("Enter days to query (leave empty for default 30 days): ")
        url = f"{self.base_url}/api/admin/analytics/user-activity"
        if days:
            url += f"?days={days}"
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
    
    def test_application_logs(self):
        print("\n=== Testing Application Logs ===")
        print("Filter options:")
        level = input("Log level (error, warning, info, etc.): ")
        source = input("Source/component: ")
        start_date = input("Start date (YYYY-MM-DD): ")
        end_date = input("End date (YYYY-MM-DD): ")
        limit = input("Limit (number of logs to return): ")
        
        params = []
        if level: params.append(f"level={level}")
        if source: params.append(f"source={source}")
        if start_date: params.append(f"start_date={start_date}T00:00:00Z")
        if end_date: params.append(f"end_date={end_date}T23:59:59Z")
        if limit: params.append(f"limit={limit}")
        
        url = f"{self.base_url}/api/admin/logs"
        if params:
            url += "?" + "&".join(params)
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
    
    def test_list_podcasts(self):
        print("\n=== Testing List Podcasts ===")
        title_search = input("Search by title (leave empty to skip): ")
        is_featured = input("Is featured (true/false, leave empty to skip): ")
        language = input("Language filter (leave empty to skip): ")
        page = input("Page number (leave empty to skip): ")
        limit = input("Items per page (leave empty to skip): ")
        
        params = []
        if title_search: params.append(f"title_search={title_search}")
        if is_featured: params.append(f"is_featured={is_featured}")
        if language: params.append(f"language={language}")
        if page: params.append(f"page={page}")
        if limit: params.append(f"limit={limit}")
        
        url = f"{self.base_url}/api/admin/podcasts"
        if params:
            url += "?" + "&".join(params)
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
        return response.json().get('data', [])
    
    def test_podcast_details(self):
        print("\n=== Testing Podcast Details ===")
        podcast_id = input("Enter podcast ID: ")
        if not podcast_id:
            print("Podcast ID is required")
            return
        
        response = requests.get(
            f"{self.base_url}/api/admin/podcasts/{podcast_id}",
            headers=self.headers
        )
        self.print_response(response)
    
    def test_update_podcast(self):
        print("\n=== Testing Update Podcast ===")
        podcast_id = input("Enter podcast ID to update: ")
        if not podcast_id:
            print("Podcast ID is required")
            return
        
        print("Enter new values (leave empty to keep current):")
        title = input("Title: ")
        description = input("Description: ")
        is_featured = input("Is featured (true/false): ")
        tags = input("Tags (comma separated): ")
        
        update_data = {}
        if title: update_data["title"] = title
        if description: update_data["description"] = description
        if is_featured: update_data["is_featured"] = is_featured.lower() == "true"
        if tags: update_data["tags"] = [tag.strip() for tag in tags.split(",")]
        
        if not update_data:
            print("No fields to update")
            return
        
        response = requests.put(
            f"{self.base_url}/api/admin/podcasts/{podcast_id}",
            headers=self.headers,
            json=update_data
        )
        self.print_response(response)
    
    def test_delete_podcast(self):
        print("\n=== Testing Delete Podcast ===")
        podcast_id = input("Enter podcast ID to delete: ")
        if not podcast_id:
            print("Podcast ID is required")
            return
        
        response = requests.delete(
            f"{self.base_url}/api/admin/podcasts/{podcast_id}",
            headers=self.headers
        )
        self.print_response(response)
    
    def test_list_transcripts(self):
        print("\n=== Testing List Transcripts ===")
        podcast_id = input("Filter by podcast ID (leave empty to skip): ")
        is_edited = input("Is edited (true/false, leave empty to skip): ")
        language = input("Language filter (leave empty to skip): ")
        
        params = []
        if podcast_id: params.append(f"podcast_id={podcast_id}")
        if is_edited: params.append(f"is_edited={is_edited}")
        if language: params.append(f"language={language}")
        
        url = f"{self.base_url}/api/admin/transcripts"
        if params:
            url += "?" + "&".join(params)
        
        response = requests.get(url, headers=self.headers)
        self.print_response(response)
    
    def test_featured_content(self):
        print("\n=== Testing Featured Content ===")
        print("1. List featured content")
        print("2. Create featured content")
        print("3. Delete featured content")
        choice = input("Enter your choice (1-3): ")
        
        if choice == "1":
            is_active = input("Filter by active status (true/false, leave empty to skip): ")
            content_type = input("Filter by content type (leave empty to skip): ")
            title_search = input("Search by title (leave empty to skip): ")
            
            params = []
            if is_active: params.append(f"is_active={is_active}")
            if content_type: params.append(f"content_type={content_type}")
            if title_search: params.append(f"title_search={title_search}")
            
            url = f"{self.base_url}/api/admin/featured-content"
            if params:
                url += "?" + "&".join(params)
            
            response = requests.get(url, headers=self.headers)
            self.print_response(response)
        
        elif choice == "2":
            print("Enter featured content details:")
            title = input("Title (required): ")
            description = input("Description (required): ")
            image_url = input("Image URL (required): ")
            target_url = input("Target URL (required): ")
            content_type = input("Content Type (podcast/transcript/etc., required): ")
            priority = input("Priority (number, default 5): ") or "5"
            is_active = input("Is active (true/false, default true): ") or "true"
            
            featured_data = {
                "title": title,
                "description": description,
                "image_url": image_url,
                "target_url": target_url,
                "content_type": content_type,
                "priority": int(priority),
                "start_date": datetime.utcnow().isoformat() + "Z",
                "end_date": (datetime.utcnow() + timedelta(days=30)).isoformat() + "Z",
                "is_active": is_active.lower() == "true"
            }
            
            response = requests.post(
                f"{self.base_url}/api/admin/featured-content",
                headers=self.headers,
                json=featured_data
            )
            self.print_response(response)
        
        elif choice == "3":
            content_id = input("Enter featured content ID to delete: ")
            if not content_id:
                print("Content ID is required")
                return
            
            response = requests.delete(
                f"{self.base_url}/api/admin/featured-content/{content_id}",
                headers=self.headers
            )
            self.print_response(response)

def main():
    print("=== Voicera Admin API Tester ===")
    base_url = input("Enter base URL (default: http://localhost:8000): ") or "http://localhost:8000"
    admin_token = input("Enter admin JWT token (leave empty to login first): ")
    
    tester = VoiceraAdminAPITester(base_url, admin_token if admin_token else None)
    
    if not admin_token:
        print("\nYou need to login first")
        token = tester.test_login()
        if not token:
            print("Login failed. Exiting.")
            return
    
    while True:
        print("\n=== Main Menu ===")
        print("1. Authentication")
        print("2. User Management")
        print("3. Analytics & Monitoring")
        print("4. Content Management")
        print("0. Exit")
        
        choice = input("Enter your choice (0-4): ")
        
        if choice == "0":
            print("Goodbye!")
            break
        
        elif choice == "1":
            print("\n=== Authentication Menu ===")
            print("1. Test Login")
            print("0. Back to Main Menu")
            sub_choice = input("Enter your choice: ")
            
            if sub_choice == "1":
                token = tester.test_login()
                if token:
                    tester.set_admin_token(token)
        
        elif choice == "2":
            while True:
                print("\n=== User Management Menu ===")
                print("1. List Users")
                print("2. Get User Details")
                print("3. Update User")
                print("4. Update User Status")
                print("5. Create User")
                print("6. Delete User")
                print("0. Back to Main Menu")
                
                sub_choice = input("Enter your choice (0-6): ")
                
                if sub_choice == "0":
                    break
                elif sub_choice == "1":
                    tester.test_list_users()
                elif sub_choice == "2":
                    tester.test_get_user_details()
                elif sub_choice == "3":
                    tester.test_update_user()
                elif sub_choice == "4":
                    tester.test_update_user_status()
                elif sub_choice == "5":
                    tester.test_create_user()
                elif sub_choice == "6":
                    tester.test_delete_user()
        
        elif choice == "3":
            while True:
                print("\n=== Analytics & Monitoring Menu ===")
                print("1. API Usage Metrics")
                print("2. Transcription Statistics")
                print("3. Search Trends")
                print("4. User Activity Data")
                print("5. Application Logs")
                print("0. Back to Main Menu")
                
                sub_choice = input("Enter your choice (0-5): ")
                
                if sub_choice == "0":
                    break
                elif sub_choice == "1":
                    tester.test_analytics_usage()
                elif sub_choice == "2":
                    tester.test_analytics_transcriptions()
                elif sub_choice == "3":
                    tester.test_analytics_search_trends()
                elif sub_choice == "4":
                    tester.test_analytics_user_activity()
                elif sub_choice == "5":
                    tester.test_application_logs()
        
        elif choice == "4":
            while True:
                print("\n=== Content Management Menu ===")
                print("1. List Podcasts")
                print("2. Get Podcast Details")
                print("3. Update Podcast")
                print("4. Delete Podcast")
                print("5. List Transcripts")
                print("6. Featured Content")
                print("0. Back to Main Menu")
                
                sub_choice = input("Enter your choice (0-6): ")
                
                if sub_choice == "0":
                    break
                elif sub_choice == "1":
                    tester.test_list_podcasts()
                elif sub_choice == "2":
                    tester.test_podcast_details()
                elif sub_choice == "3":
                    tester.test_update_podcast()
                elif sub_choice == "4":
                    tester.test_delete_podcast()
                elif sub_choice == "5":
                    tester.test_list_transcripts()
                elif sub_choice == "6":
                    tester.test_featured_content()

if __name__ == "__main__":
    main()