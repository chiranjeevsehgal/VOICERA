-- Create the user_uploads table to track file ownership
create table if not exists user_uploads (
    id uuid default uuid_generate_v4() primary key,
    user_id text not null,  -- Changed to text to store MongoDB ObjectId as string
    file_name text not null,
    file_path text not null,
    file_url text not null,
    metadata jsonb,
    created_at timestamp with time zone default timezone('utc'::text, now()) not null,
    updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

-- Enable RLS
alter table user_uploads enable row level security;

-- Create a more permissive policy for our MongoDB auth setup
create policy "Enable read access for all users"
    on user_uploads for select
    using (true);  -- Anyone can read the records

create policy "Enable insert for all authenticated requests"
    on user_uploads for insert
    with check (true);  -- Trust our application layer authentication

create policy "Enable update for all authenticated requests"
    on user_uploads for update
    using (true);  -- Trust our application layer authentication

create policy "Enable delete for all authenticated requests"
    on user_uploads for delete
    using (true);  -- Trust our application layer authentication

-- Create updated_at trigger
create trigger handle_updated_at before update on user_uploads
    for each row execute procedure extensions.moddatetime(); 