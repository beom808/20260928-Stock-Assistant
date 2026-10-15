-- Supabase 에서 GitHub Actions 를 정시에 깨우는 스케줄러 (pg_cron + pg_net + Vault)
--
-- 왜: GitHub 자체 예약(schedule)이 2026-10-14~15 에 지연·누락됐다(15:40 실행 누락, 07:00/07:30 미시작).
--     DB 안의 pg_cron 이 정시에 GitHub 의 workflow_dispatch 를 호출해 같은 작업을 시작시킨다.
--     GitHub 자체 예약과 --skip-existing 덕분에 중복 발행·알림은 생기지 않는다.
--
-- 사용 순서는 infra/scheduler.md 의 "Supabase 스케줄러" 참고. 이 파일에는 비밀값이 없다.
--   0) Supabase 대시보드 → Database → Extensions 에서 pg_cron, pg_net 을 켠다.
--   1) 대시보드 → Database → Vault → Add new secret
--        Name  : github_dispatch_token
--        Secret: GitHub 세밀한 토큰(이 저장소 하나, Actions: Read and write)  ← 채팅에 붙여 넣지 말 것
--   2) 아래 SQL 을 SQL Editor 에 통째로 붙여 넣고 Run.
--
-- 시각은 UTC 기준(pg_cron 기본). KST = UTC+9, 한국은 서머타임이 없어 고정이다.
--   07:00 KST = 22:00 UTC (일~목)   15:40 KST = 06:40 UTC (월~금)

create extension if not exists pg_cron;
create extension if not exists pg_net;

-- 외부(PostgREST/anon 키)에서 호출할 수 없도록 API 로 노출되지 않는 별도 스키마에 둔다
create schema if not exists private;
revoke all on schema private from public, anon, authenticated;

create or replace function private.trigger_report(
  p_reports text,                          -- 'morning' | 'afternoon' | 'all'
  p_skip_existing boolean default true,    -- 오늘 리포트가 이미 있으면 건너뜀
  p_dry_run boolean default false          -- true 면 저장·알림 없는 테스트 실행(AI 도 끔)
) returns bigint
language plpgsql
security definer
set search_path = ''
as $$
declare
  tok text;
  req_id bigint;
begin
  if p_reports not in ('morning', 'afternoon', 'all') then
    raise exception 'p_reports must be morning, afternoon or all';
  end if;

  select decrypted_secret into tok
  from vault.decrypted_secrets
  where name = 'github_dispatch_token'
  limit 1;
  if tok is null then
    raise exception 'Vault secret github_dispatch_token not found';
  end if;

  select net.http_post(
    url := 'https://api.github.com/repos/beom808/20260928-Stock-Assistant/actions/workflows/reports.yml/dispatches',
    headers := jsonb_build_object(
      'Authorization', 'Bearer ' || tok,
      'Accept', 'application/vnd.github+json',
      'X-GitHub-Api-Version', '2022-11-28',
      'User-Agent', 'stock-assistant-supabase-scheduler',
      'Content-Type', 'application/json'
    ),
    body := jsonb_build_object(
      'ref', 'main',
      'inputs', jsonb_build_object(
        'reports', p_reports,
        'force', 'false',
        'dry_run', p_dry_run::text,
        'skip_ai', p_dry_run::text,
        'skip_existing', p_skip_existing::text
      )
    ),
    timeout_milliseconds := 10000
  ) into req_id;

  return req_id;  -- net._http_response 에서 이 id 로 결과(성공이면 status_code 204)를 본다
end;
$$;

revoke all on function private.trigger_report(text, boolean, boolean) from public, anon, authenticated;

-- 예약(UTC). 같은 이름으로 다시 실행하면 덮어쓴다.
select cron.schedule('report-morning',         '0 22 * * 0-4',  $$select private.trigger_report('morning',   true, false)$$);
select cron.schedule('report-morning-retry',   '20 22 * * 0-4', $$select private.trigger_report('morning',   true, false)$$);
select cron.schedule('report-afternoon',       '40 6 * * 1-5',  $$select private.trigger_report('afternoon', true, false)$$);
select cron.schedule('report-afternoon-retry', '0 7 * * 1-5',   $$select private.trigger_report('afternoon', true, false)$$);

-- ── 점검용(원할 때 따로 실행) ─────────────────────────────────────────────
-- 등록된 예약:        select jobid, jobname, schedule, active from cron.job order by jobname;
-- 최근 실행 기록:     select jobname, status, start_time, return_message
--                     from cron.job_run_details d join cron.job j using (jobid)
--                     order by start_time desc limit 10;
--                     (여기서는 '호출을 요청했다'까지만 보인다)
-- GitHub 응답(204=성공): select id, status_code, left(content::text, 200) as content, created
--                     from net._http_response order by created desc limit 10;
-- 알림·저장 없는 테스트: select private.trigger_report('afternoon', false, true);
-- 예약 끄기:          select cron.unschedule('report-morning');  -- 이름별로
