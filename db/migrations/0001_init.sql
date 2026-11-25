-- =====================================================================
-- 白石農園 データ一元化システム：初期テーブル（Supabase / Postgres）
-- 使い方: Supabase の SQL Editor に貼り付けて実行する（1回だけ）
-- 方針:
--   * 日報は「元の本文をそのまま残す」→ AIの読み取り結果は別テーブル
--   * 日報とハウスは中間テーブル（report_houses）でつなぐ（1件に複数ハウス）
--   * ハウス一覧は AI が日報から育てる。迷うものは status='candidate'
--   * 時刻はすべて timestamptz（UTCで保存、表示は日本時間）
--   * 全テーブルで RLS を有効にし、ポリシーは作らない
--     → ブラウザ用の anon キーからは読めない。ボット（サーバー）は
--       DB直結または service_role キーで読み書きする
-- =====================================================================

-- ---------------------------------------------------------------------
-- 人とグループ
-- ---------------------------------------------------------------------

-- 利用者。プロバイダーが別なので、同じ人でもボットごとにLINEのIDが違う
create table users (
  id                      bigint generated always as identity primary key,
  display_name            text not null,                -- LINEの表示名（取り込み時の名前）
  report_line_user_id     text unique,                  -- 日報ボット（FunFirm）側のID
  assistant_line_user_id  text unique,                  -- 管理ボット（FunFirm_host）側のID
  role                    text not null default 'staff'
                          check (role in ('admin', 'staff')),  -- admin=管理者3人 / staff=パートさん等
  created_at              timestamptz not null default now()
);

-- ボットが入っているLINEグループ
create table line_groups (
  id          text primary key,                         -- LINEのグループID（C...）
  kind        text not null check (kind in ('report', 'admin', 'test')),
  name        text,
  joined_at   timestamptz not null default now(),
  left_at     timestamptz
);

-- ---------------------------------------------------------------------
-- 日報
-- ---------------------------------------------------------------------

-- 日報（同じ人が続けて投稿した文字・写真を1件にまとめたもの）
create table daily_reports (
  id                 bigint generated always as identity primary key,
  group_id           text references line_groups(id),
  report_date        date not null,                    -- 投稿日（日本時間）
  user_id            bigint references users(id),
  sender_name        text not null,                    -- 取り込み時の表示名（users が未登録でも残す）
  started_at         timestamptz not null,
  ended_at           timestamptz not null,
  body               text not null default '',         -- 元の本文をつなげたもの（書き換えない）
  -- AIの読み取り
  extraction_status  text not null default 'pending'
                     check (extraction_status in ('pending', 'done', 'failed', 'skipped')),
  extracted_at       timestamptz,
  extraction_model   text,
  extraction_raw     jsonb,                            -- AIが返した内容（見直し・読み直し用）
  created_at         timestamptz not null default now()
);
create index daily_reports_date_idx on daily_reports (report_date);
create index daily_reports_status_idx on daily_reports (extraction_status);

-- LINEのメッセージ1件ずつの元データ（文字・写真・ファイル）
create table line_messages (
  id                 text primary key,                 -- LINEのメッセージID（履歴取り込み分は imp- で始まる）
  group_id           text references line_groups(id),
  report_id          bigint references daily_reports(id) on delete set null,
  user_id            bigint references users(id),
  sender_name        text not null,
  sent_at            timestamptz not null,
  type               text not null,                    -- text / image / file / video / sticker など
  text               text,
  quoted_message_id  text,                             -- 引用返信の元（写真への説明文などをつなぐ）
  source             text not null default 'line_bot'
                     check (source in ('line_bot', 'import')),
  raw                jsonb,                            -- LINEから届いた元のイベント
  received_at        timestamptz not null default now()
);
create index line_messages_group_sent_idx on line_messages (group_id, sent_at);
create index line_messages_report_idx on line_messages (report_id);

-- 写真・ファイル（実体は Supabase Storage の line-attachments バケット）
create table attachments (
  id            bigint generated always as identity primary key,
  message_id    text not null unique references line_messages(id) on delete cascade,
  report_id     bigint references daily_reports(id) on delete set null,
  kind          text not null check (kind in ('image', 'file', 'video')),
  storage_path  text not null,                         -- 例: groups/<グループID>/2026-11-25/<メッセージID>.jpg
  file_name     text,
  mime_type     text,
  size_bytes    bigint,
  sent_at       timestamptz not null,
  created_at    timestamptz not null default now()
);
create index attachments_report_idx on attachments (report_id);

-- ---------------------------------------------------------------------
-- ハウス（AIが日報から育てる）
-- ---------------------------------------------------------------------

create table houses (
  id           bigint generated always as identity primary key,
  name         text not null,                          -- 表示名（例: 3番ハウス、A棟3、山の畑）
  kind         text not null default 'house'
               check (kind in ('house', 'field', 'other')),  -- ハウス / 露地 / その他
  status       text not null default 'candidate'
               check (status in ('confirmed', 'candidate')), -- 確定 / AIが作った候補
  created_by   text not null default 'ai' check (created_by in ('ai', 'human')),
  merged_into  bigint references houses(id),           -- 別のハウスに統合されたら統合先
  note         text,
  created_at   timestamptz not null default now()
);

-- 書かれ方（表記ゆれ）。normalized で照合する
create table house_aliases (
  id          bigint generated always as identity primary key,
  house_id    bigint not null references houses(id) on delete cascade,
  alias       text not null,                           -- 書かれていたまま（例: A-3、A棟3）
  normalized  text not null unique,                    -- 全角→半角・空白や記号を除いたもの
  created_by  text not null default 'ai' check (created_by in ('ai', 'human')),
  created_at  timestamptz not null default now()
);

-- 日報とハウス（1件の日報に複数のハウス）
create table report_houses (
  report_id     bigint not null references daily_reports(id) on delete cascade,
  house_id      bigint not null references houses(id),
  raw_label     text,                                  -- 書かれていた表記（例: 5.4.3、453）
  is_inferred   boolean not null default false,        -- 本文に明記がなくAIが推定したもの
  confidence    real,                                  -- AIの確信度（0〜1）
  primary key (report_id, house_id)
);
create index report_houses_house_idx on report_houses (house_id);

-- 日報から読み取った作業（「昨日」なども日付にして持つ）
create table report_tasks (
  id                bigint generated always as identity primary key,
  report_id         bigint not null references daily_reports(id) on delete cascade,
  work_date         date not null,
  task              text not null,                     -- 例: 水やり、トマトトーン、収穫
  quantity          numeric,                           -- 次フェーズ用（収穫量など。書いてあれば入れる）
  unit              text,
  duration_minutes  integer,                           -- 次フェーズ用（作業時間）
  note              text
);
create index report_tasks_report_idx on report_tasks (report_id);
create index report_tasks_date_idx on report_tasks (work_date);

-- 作業とハウス（「5.4.3のトマトトーン、1,3水やり」のように作業ごとにハウスが違う場合）
create table task_houses (
  task_id   bigint not null references report_tasks(id) on delete cascade,
  house_id  bigint not null references houses(id),
  primary key (task_id, house_id)
);

-- ---------------------------------------------------------------------
-- センサー（ファーモのCSV）
-- ---------------------------------------------------------------------

create table sensors (
  device_id   text primary key,                        -- CSVに入っている機器ID
  house_id    bigint references houses(id),            -- 分からなければ空でよい
  name        text,
  created_at  timestamptz not null default now()
);

-- 取り込んだCSVファイル1つ = 1行
create table sensor_imports (
  id             bigint generated always as identity primary key,
  file_name      text not null,
  storage_path   text,                                 -- 元のCSV（Storage）
  uploaded_by    bigint references users(id),
  period_start   timestamptz,
  period_end     timestamptz,
  rows_inserted  integer not null default 0,
  rows_skipped   integer not null default 0,
  imported_at    timestamptz not null default now()
);

create table sensor_readings (
  device_id    text not null references sensors(device_id),
  measured_at  timestamptz not null,
  temperature  numeric,                                -- ℃
  humidity     numeric,                                -- %
  extra        jsonb,                                  -- そのほかの列（CO2、土壌水分など）
  import_id    bigint references sensor_imports(id),
  primary key (device_id, measured_at)                 -- 同じCSVを2回送っても重複しない
);
create index sensor_readings_time_idx on sensor_readings (measured_at);

-- ---------------------------------------------------------------------
-- 気象（アメダスの10分値）
-- ---------------------------------------------------------------------

create table weather_obs (
  station_id        text not null,                     -- アメダスの地点番号
  observed_at       timestamptz not null,
  temperature       numeric,                           -- ℃
  humidity          numeric,                           -- %
  precipitation_10m numeric,                           -- mm（10分間）
  wind_speed        numeric,                           -- m/s
  wind_direction    smallint,                          -- 16方位（気象庁のコード）
  sunshine_10m      numeric,                           -- 分（10分間の日照）
  raw               jsonb,
  primary key (station_id, observed_at)
);

-- ---------------------------------------------------------------------
-- 運用の記録
-- ---------------------------------------------------------------------

-- 質問と回答の記録（答えられなかった質問 = 日報に足りない情報の手がかり）
create table question_logs (
  id              bigint generated always as identity primary key,
  user_id         bigint references users(id),
  group_id        text references line_groups(id),     -- 1対1なら空
  asked_at        timestamptz not null default now(),
  question        text not null,
  answer          text,
  answerable      boolean,                             -- データ不足で答えられなかったら false
  missing_info    text,                                -- 何が足りなかったか
  model           text,
  input_tokens    integer,
  output_tokens   integer
);

-- 週次レポートの送信記録（送り直し・二重送信の防止）
create table weekly_reports (
  id          bigint generated always as identity primary key,
  week_start  date not null unique,                    -- その週の月曜日
  sent_at     timestamptz,
  sent_to     text,                                    -- 送り先のグループID
  summary     jsonb                                    -- 送った内容の数字
);

-- ---------------------------------------------------------------------
-- セキュリティ: すべてのテーブルで RLS を有効にする（ポリシーなし）
-- ---------------------------------------------------------------------
alter table users            enable row level security;
alter table line_groups      enable row level security;
alter table daily_reports    enable row level security;
alter table line_messages    enable row level security;
alter table attachments      enable row level security;
alter table houses           enable row level security;
alter table house_aliases    enable row level security;
alter table report_houses    enable row level security;
alter table report_tasks     enable row level security;
alter table task_houses      enable row level security;
alter table sensors          enable row level security;
alter table sensor_imports   enable row level security;
alter table sensor_readings  enable row level security;
alter table weather_obs      enable row level security;
alter table question_logs    enable row level security;
alter table weekly_reports   enable row level security;

-- ---------------------------------------------------------------------
-- Storage: 写真・ファイル・CSV 用の非公開バケット
-- ---------------------------------------------------------------------
insert into storage.buckets (id, name, public)
values ('line-attachments', 'line-attachments', false)
on conflict (id) do nothing;
