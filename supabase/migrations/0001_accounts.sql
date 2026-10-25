-- Apply in Supabase SQL Editor before enabling accounts. No service-role key is used.
create table public.account_workspaces (
  user_id uuid primary key references auth.users(id) on delete cascade,
  workspace jsonb not null,
  revision bigint not null default 1,
  updated_at timestamptz not null default now(),
  check (octet_length(workspace::text) <= 12582912)
);
alter table public.account_workspaces enable row level security;
create policy own_workspace on public.account_workspaces for all to authenticated
  using ((select auth.uid()) = user_id)
  with check ((select auth.uid()) = user_id);
revoke all on public.account_workspaces from anon, authenticated;
grant select on public.account_workspaces to authenticated;

create table public.account_drafts (
  user_id uuid not null references auth.users(id) on delete cascade,
  turn_id uuid not null,
  answer text not null check (length(answer) <= 20000),
  revision bigint not null default 1,
  primary key (user_id, turn_id)
);
alter table public.account_drafts enable row level security;
create policy own_drafts on public.account_drafts for select to authenticated
  using ((select auth.uid()) = user_id);
revoke all on public.account_drafts from anon, authenticated;
grant select on public.account_drafts to authenticated;
create function public.save_account_draft(turn uuid, answer_text text, expected_revision bigint)
returns bigint language plpgsql security definer set search_path = '' as $$
declare current_revision bigint;
begin
  if auth.uid() is null or not exists (
    select 1 from auth.users where id = auth.uid() and email_confirmed_at is not null
  ) then raise exception 'Authentication required' using errcode = '42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));
  select revision into current_revision from public.account_drafts
    where user_id = auth.uid() and turn_id = turn;
  if coalesce(current_revision, 0) <> expected_revision then
    raise exception 'Revision conflict' using errcode = 'P0001';
  end if;
  insert into public.account_drafts(user_id, turn_id, answer, revision)
    values (auth.uid(), turn, answer_text, 1)
    on conflict (user_id, turn_id) do update set answer = answer_text,
      revision = account_drafts.revision + 1
    returning revision into current_revision;
  return current_revision;
end $$;
revoke all on function public.save_account_draft(uuid, text, bigint) from public, anon;
grant execute on function public.save_account_draft(uuid, text, bigint) to authenticated;

create function public.save_account_workspace(payload jsonb, expected_revision bigint)
returns bigint language plpgsql security definer set search_path = '' as $$
declare current_revision bigint;
begin
  if auth.uid() is null or not exists (
    select 1 from auth.users where id = auth.uid() and email_confirmed_at is not null
  ) then raise exception 'Authentication required' using errcode = '42501'; end if;
  perform pg_advisory_xact_lock(hashtextextended(auth.uid()::text, 0));
  select revision into current_revision from public.account_workspaces where user_id = auth.uid();
  if coalesce(current_revision, 0) <> expected_revision then
    raise exception 'Revision conflict' using errcode = 'P0001';
  end if;
  insert into public.account_workspaces(user_id, workspace, revision)
    values (auth.uid(), payload, 1)
    on conflict (user_id) do update set workspace = payload,
      revision = account_workspaces.revision + 1, updated_at = now()
    returning revision into current_revision;
  return current_revision;
end $$;
revoke all on function public.save_account_workspace(jsonb, bigint) from public, anon;
grant execute on function public.save_account_workspace(jsonb, bigint) to authenticated;

create function public.delete_own_account()
returns void language plpgsql security definer set search_path = '' as $$
begin
  if auth.uid() is null then raise exception 'Authentication required'; end if;
  delete from auth.users where id = auth.uid();
end $$;
revoke all on function public.delete_own_account() from public, anon;
grant execute on function public.delete_own_account() to authenticated;
