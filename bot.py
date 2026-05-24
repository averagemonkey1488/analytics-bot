#!/usr/bin/env python3
"""TD Analytics Toolkit Bot — OAuth edition"""

import asyncio
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── write service_account.json from env var (kept for fallback) ─
_sa_raw = os.getenv("SERVICE_ACCOUNT_JSON", "")
if _sa_raw:
    try:
        with open("service_account.json", "w") as _f:
            json.dump(json.loads(_sa_raw), _f, indent=2)
        print("service_account.json written OK")
    except Exception as _e:
        print(f"WARNING: SERVICE_ACCOUNT_JSON parse failed: {_e}")

# ── write token.json from env var ───────────────────────────────
_tok_raw = os.getenv("GOOGLE_TOKEN_JSON", "").strip()
if _tok_raw:
    try:
        # Strip surrounding quotes if Railway added them
        if _tok_raw.startswith('"') and _tok_raw.endswith('"'):
            _tok_raw = _tok_raw[1:-1]
        # Unescape if Railway escaped the quotes
        _tok_raw = _tok_raw.replace('\"', '"')
        _tok_data = json.loads(_tok_raw)
        with open("token.json", "w") as _f:
            json.dump(_tok_data, _f, indent=2)
        print(f"token.json written OK (refresh_token present: {bool(_tok_data.get('refresh_token'))})")
    except Exception as _e:
        print(f"WARNING: GOOGLE_TOKEN_JSON parse failed: {_e}")
        print(f"  Raw value starts with: {_tok_raw[:50]!r}")
else:
    print("WARNING: GOOGLE_TOKEN_JSON env var is empty or not set")
# ────────────────────────────────────────────────────────────────

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from google.oauth2.credentials import Credentials as OAuthCredentials
from google.oauth2.service_account import Credentials as SACredentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════

BOT_TOKEN            = os.getenv("BOT_TOKEN", "")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
TOKEN_FILE           = "token.json"
DATA_FILE            = os.getenv("DATA_FILE", "data.json")
FIRST_ADMIN_ID       = int(os.getenv("FIRST_ADMIN_ID", "0"))

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.projects",
]

# ═══════════════════════════════════════════════════════════════
# PLATFORMS
# ═══════════════════════════════════════════════════════════════

PLATFORMS: dict = {
    "cellexpert": {
        "name": "🎯 Cellexpert",
        "library_symbol": "ChinCore",
        "fields": {
            "webname":        {"label": "Webname field",  "default": "afp2", "options": ["afp1","afp2","afp3","afp4","afp6","afp10"]},
            "creo":           {"label": "Creo field",     "default": "afp6", "options": ["afp1","afp2","afp3","afp4","afp6","afp10"]},
            "clickid":        {"label": "Click ID field", "default": "afp1", "options": ["afp1","afp2","afp3","afp4","afp6","afp10"]},
            "target_oas":     {"label": "Target OAS",     "default": "55%"},
            "hr_top_percent": {"label": "HR Top %",       "default": "2%"},
        },
        "public_api": {
            "quality": "processFullReportBoth_Public", "oas": "buildOASByWebBoth_Public",
            "export": "exportWebnameReports_Public",   "root_index": "openRootIndex_Public",
            "ex_config": "createExportConfig_Public",  "debug_map": "debugExportMapping_Public",
            "stop": "stopExport_Public",               "reset": "hardResetExportCache_Public",
            "chunk": "EX_exportChunk_Public",          "ping": "ChinCore_ping_Public",
        },
    },
    "referon": {
        "name": "📊 ReferOn",
        "library_symbol": "TDCore",
        "fields": {
            "webname":     {"label": "Webname field",  "default": "pubid",   "options": ["pubid","subid","var1","var2","var3","var4","var5","clickid"]},
            "creo":        {"label": "Creo field",     "default": "var3",    "options": ["var1","var2","var3","var4","var5","pubid","subid"]},
            "clickid":     {"label": "Click ID field", "default": "clickid", "options": ["clickid","click_id","var1","var2","var3","var4","var5"]},
            "target_oas":  {"label": "Target OAS",     "default": "55%"},
            "min_ftd_gate":{"label": "Min FTD Gate",   "default": "5"},
        },
        "public_api": {
            "quality": "processAllPrograms_Public",          "oas": "buildOASByWeb_Public",
            "export": "exportFeedsByRealWebname_Public",     "root_index": "openRootIndex_Public",
            "ex_config": "openExportConfig_Public",          "debug_map": "debugExportMapping_Public",
            "stop": "stopExportAndReset_Public",             "reset": "resetCache_Public",
            "chunk": "EX_exportChunk_Public",                "ping": "CPCore_ping_Public",
        },
    },
    "affilka_fb": {
        "name": "📱 Affilka FB",
        "library_symbol": "FBCore",
        "fields": {
            "webname":        {"label": "Webname field",  "default": "afp1", "options": ["afp1","afp2","afp3","afp4","afp10","promo_code","promo_name"]},
            "creo":           {"label": "Creo field",     "default": "afp1", "options": ["afp1","afp2","afp3","afp4","afp10","promo_code","promo_name"]},
            "clickid":        {"label": "Click ID field", "default": "afp3", "options": ["afp1","afp2","afp3","afp4","afp10"]},
            "target_oas":     {"label": "Target OAS",     "default": "55%"},
            "hr_top_percent": {"label": "HR Top %",       "default": "2%"},
            "min_ftd_gate":   {"label": "Min FTD Gate",   "default": "5"},
        },
        "public_api": {
            "quality": "processAllPrograms_Public",         "oas": "buildOASByWeb_Public",
            "export": "exportFeedsByRealWebname_Public",    "root_index": "openRootIndex_Public",
            "ex_config": "openExportConfig_Public",         "debug_map": "debugExportMapping_Public",
            "normalize": "normalizeRawData_Public",         "debug_raw": "debugRawValues_Public",
            "stop": "stopExportAndReset_Public",            "reset": "resetCache_Public",
            "chunk": "EX_exportChunk_Public",               "ping": "CPCore_ping_Public",
        },
    },
    "affilka": {
        "name": "🔗 Affilka Standard",
        "library_symbol": "TDCoreV5",
        "fields": {
            "webname":     {"label": "Webname field",  "default": "pubid",   "options": ["pubid","subid","var1","var2","var3","var4","var5"]},
            "creo":        {"label": "Creo field",     "default": "var3",    "options": ["var1","var2","var3","var4","var5","pubid"]},
            "clickid":     {"label": "Click ID field", "default": "clickid", "options": ["clickid","var1","var2","var3","var4","var5"]},
            "target_oas":  {"label": "Target OAS",     "default": "55%"},
            "min_ftd_gate":{"label": "Min FTD Gate",   "default": "5"},
        },
        "public_api": {
            "quality": "processAllPrograms_Public",         "oas": "buildOASByWeb_Public",
            "export": "exportFeedsByRealWebname_Public",    "root_index": "openRootIndex_Public",
            "ex_config": "openExportConfig_Public",         "debug_map": "debugExportMapping_Public",
            "stop": "stopExportAndReset_Public",            "reset": "resetCache_Public",
            "chunk": "EX_exportChunk_Public",               "ping": "CPCore_ping_Public",
        },
    },
}

WIZARD_STEPS = ["webname", "creo", "clickid", "target_oas", "min_ftd_gate", "hr_top_percent"]


# ═══════════════════════════════════════════════════════════════
# CREDENTIALS LOADER
# ═══════════════════════════════════════════════════════════════

def load_google_credentials():
    """
    Priority:
      1. token.json  (OAuth — user's own Google account, has full Drive access)
      2. service_account.json (fallback)
    """
    # Try OAuth token first
    if Path(TOKEN_FILE).exists():
        try:
            data  = json.loads(Path(TOKEN_FILE).read_text())
            creds = OAuthCredentials(
                token=data.get("token"),
                refresh_token=data.get("refresh_token"),
                token_uri=data.get("token_uri", "https://oauth2.googleapis.com/token"),
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
                scopes=data.get("scopes", GOOGLE_SCOPES),
            )
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                log.info("OAuth token refreshed")
            log.info("Using OAuth credentials (token.json)")
            return creds
        except Exception as e:
            log.warning("token.json failed: %s", e)

    # Try service account
    if Path(SERVICE_ACCOUNT_FILE).exists():
        log.info("Using service account credentials")
        return SACredentials.from_service_account_file(SERVICE_ACCOUNT_FILE, scopes=GOOGLE_SCOPES)

    # No credentials at all — show helpful error but don't crash
    log.error("No credentials found! Set GOOGLE_TOKEN_JSON env var.")
    raise RuntimeError(
        "No Google credentials found.\n"
        "Set GOOGLE_TOKEN_JSON in Railway Variables.\n"
        f"token.json exists: {Path(TOKEN_FILE).exists()}\n"
        f"service_account.json exists: {Path(SERVICE_ACCOUNT_FILE).exists()}\n"
        f"GOOGLE_TOKEN_JSON env var set: {bool(os.getenv('GOOGLE_TOKEN_JSON'))}"
    )


# ═══════════════════════════════════════════════════════════════
# GAS SCRIPT GENERATOR
# ═══════════════════════════════════════════════════════════════

def build_loader_script(platform_key: str) -> str:
    p   = PLATFORMS[platform_key]
    sym = p["library_symbol"]
    api = p["public_api"]

    analysis_items = [
        "    .addItem('📈 Quality Tracking', '_runQuality')",
        "    .addItem('🎯 OAS Tracking',      '_runOAS')",
        "    .addSeparator()",
        "    .addItem('📦 Webname Export',    '_runExport')",
        "    .addItem('🗂 Open Root Index',   '_runRootIndex')",
    ]
    if platform_key == "affilka_fb":
        analysis_items += ["    .addSeparator()", "    .addItem('🔧 Normalize Raw Data', '_runNormalize')"]

    tech_items = [
        "    .addItem('⚙️ Export Config',       '_runExConfig')",
        "    .addItem('🔍 Debug Export Mapping', '_runDebugMap')",
    ]
    if platform_key == "affilka_fb":
        tech_items.append("    .addItem('🔢 Debug Raw Values', '_runDebugRaw')")
    tech_items += [
        "    .addSeparator()",
        "    .addItem('🛑 Stop / Reset Export', '_runStop')",
        "    .addSeparator()",
        "    .addItem('💥 HARD Reset Cache',    '_runReset')",
        "    .addSeparator()",
        "    .addItem('✅ Test Connection',     '_runPing')",
    ]

    def fn(name, call):
        return f"function {name}() {{ {sym}.{call}(); }}"

    fns = [
        fn("_runQuality",   api["quality"]),
        fn("_runOAS",       api["oas"]),
        fn("_runExport",    api["export"]),
        fn("_runRootIndex", api["root_index"]),
        fn("_runExConfig",  api["ex_config"]),
        fn("_runDebugMap",  api["debug_map"]),
        fn("_runStop",      api["stop"]),
        fn("_runReset",     api["reset"]),
        f"function EX_exportChunk_Loader() {{ {sym}.{api['chunk']}(); }}",
    ]
    if platform_key == "affilka_fb":
        fns += [fn("_runNormalize", api["normalize"]), fn("_runDebugRaw", api["debug_raw"])]
    fns.append(
        f"function _runPing() {{\n"
        f"  var r = {sym}.{api['ping']}();\n"
        f"  SpreadsheetApp.getUi().alert(r);\n"
        f"}}"
    )
    nl = "\n"
    return (
        f"// Auto-generated — {p['name']} — {datetime.utcnow():%Y-%m-%d %H:%M} UTC\n"
        f"// Library: {sym}\n\n"
        f"function onOpen() {{\n"
        f"  var ui = SpreadsheetApp.getUi();\n"
        f"  ui.createMenu('📊 ANALYSIS')\n{nl.join(analysis_items)}\n    .addToUi();\n"
        f"  ui.createMenu('🛠 TECH PANEL')\n{nl.join(tech_items)}\n    .addToUi();\n"
        f"}}\n\n"
        + "\n".join(fns)
    )


def build_manifest(library_symbol: str, script_id: str) -> str:
    return json.dumps({
        "timeZone": "Europe/London",
        "dependencies": {"libraries": [{
            "userSymbol": library_symbol, "scriptId": script_id,
            "version": "0", "developmentMode": True,
        }]},
        "exceptionLogging": "STACKDRIVER",
        "runtimeVersion": "V8",
    }, indent=2)


# ═══════════════════════════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════════════════════════

class Storage:
    def __init__(self, path: str):
        self._path = path
        self._d    = self._load()

    def _load(self) -> dict:
        if Path(self._path).exists():
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        return {"admins": [], "mother_sheets": {}, "partners": {}}

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._d, f, indent=2, ensure_ascii=False)

    def is_admin(self, uid: int) -> bool:
        return uid in self._d["admins"]

    def add_admin(self, uid: int):
        if uid and uid not in self._d["admins"]:
            self._d["admins"].append(uid); self._save()

    def add_mother_sheet(self, sheet_id, name, script_id, platform) -> dict:
        entry = {"id": sheet_id, "name": name, "script_id": script_id, "platform": platform,
                 "library_symbol": PLATFORMS[platform]["library_symbol"],
                 "created_at": datetime.utcnow().isoformat()}
        self._d["mother_sheets"][sheet_id] = entry; self._save(); return entry

    def get_mother_sheet(self, sid: str) -> Optional[dict]:
        return self._d["mother_sheets"].get(sid)

    def all_mother_sheets(self) -> dict:
        return self._d["mother_sheets"]

    def remove_mother_sheet(self, sid: str):
        self._d["mother_sheets"].pop(sid, None); self._save()

    def add_partner(self, uid: int, name: str, username: str = "") -> dict:
        entry = {"telegram_id": uid, "name": name, "username": username,
                 "assigned_sheet_ids": [], "child_sheets": [], "active": True,
                 "created_at": datetime.utcnow().isoformat()}
        self._d["partners"][str(uid)] = entry; self._save(); return entry

    def get_partner(self, uid: int) -> Optional[dict]:
        return self._d["partners"].get(str(uid))

    def all_partners(self) -> dict:
        return self._d["partners"]

    def update_partner(self, uid: int, patch: dict):
        p = self.get_partner(uid)
        if p: p.update(patch); self._d["partners"][str(uid)] = p; self._save()

    def assign_sheet(self, uid: int, sid: str):
        p = self.get_partner(uid)
        if p and sid not in p["assigned_sheet_ids"]:
            p["assigned_sheet_ids"].append(sid); self._save()

    def unassign_sheet(self, uid: int, sid: str):
        p = self.get_partner(uid)
        if p and sid in p["assigned_sheet_ids"]:
            p["assigned_sheet_ids"].remove(sid); self._save()

    def add_child_sheet(self, uid: int, child: dict):
        p = self.get_partner(uid)
        if p: p["child_sheets"].append(child); self._save()

    def partner_assigned_sheets(self, uid: int) -> list:
        p = self.get_partner(uid)
        if not p: return []
        return [self.get_mother_sheet(s) for s in p["assigned_sheet_ids"] if self.get_mother_sheet(s)]


# ═══════════════════════════════════════════════════════════════
# GOOGLE API
# ═══════════════════════════════════════════════════════════════

class GoogleAPI:
    def __init__(self):
        creds        = load_google_credentials()
        self._creds  = creds
        self._sheets = build("sheets", "v4", credentials=creds)
        self._drive  = build("drive",  "v3", credentials=creds)
        self._script = build("script", "v1", credentials=creds)
        log.info("Google API initialized")

    def _create_spreadsheet(self, title: str) -> dict:
        """Create Google Sheet via Drive API (works for both OAuth and service accounts)."""
        res = self._drive.files().create(
            body={"name": title, "mimeType": "application/vnd.google-apps.spreadsheet"},
            fields="id,webViewLink",
        ).execute()
        fid = res["id"]
        url = res.get("webViewLink", f"https://docs.google.com/spreadsheets/d/{fid}/edit")
        log.info("Sheet created: %s", fid)
        return {"id": fid, "url": url}

    def _share_anyone_write(self, file_id: str):
        self._drive.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "writer"},
            fields="id",
        ).execute()

    def _create_bound_script(self, spreadsheet_id: str, title: str) -> str:
        res = self._script.projects().create(
            body={"title": title, "parentId": spreadsheet_id}
        ).execute()
        log.info("Script created: %s", res["scriptId"])
        return res["scriptId"]

    def _push_script_files(self, script_id: str, loader_js: str, manifest_json: str):
        self._script.projects().updateContent(
            scriptId=script_id,
            body={"files": [
                {"name": "appsscript", "type": "JSON",      "source": manifest_json},
                {"name": "Loader",     "type": "SERVER_JS", "source": loader_js},
            ]},
        ).execute()

    def create_child_sheet(self, partner_name: str, platform_key: str, mother: dict) -> dict:
        plat      = PLATFORMS[platform_key]
        title     = f"{partner_name} — {plat['name']} Analytics"
        ss        = self._create_spreadsheet(title)
        loader    = build_loader_script(platform_key)
        manifest  = build_manifest(plat["library_symbol"], mother["script_id"])
        script_id = self._create_bound_script(ss["id"], f"{title} Script")
        self._push_script_files(script_id, loader, manifest)
        self._share_anyone_write(ss["id"])
        return {
            "spreadsheet_id":  ss["id"],
            "spreadsheet_url": ss["url"],
            "script_id":       script_id,
            "platform":        platform_key,
            "mother_sheet_id": mother["id"],
            "created_at":      datetime.utcnow().isoformat(),
        }


# ═══════════════════════════════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════════════════════════════

class AdminSt(StatesGroup):
    add_partner_id   = State(); add_partner_name = State()
    add_sheet_id     = State(); add_sheet_name   = State()
    add_script_id    = State(); add_platform     = State()

class PartnerSt(StatesGroup):
    pick_mother = State(); config_step = State(); confirm = State()


# ═══════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════

def _ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def _btn(text, data): return InlineKeyboardButton(text=text, callback_data=data)

def kb_admin_home():
    return _ik([_btn("👥 Partners","adm_partners"), _btn("📋 Mother Sheets","adm_sheets")],
               [_btn("🔗 Assign Sheets","adm_assign_sel")])

def kb_admin_partners(partners):
    rows = [[_btn(f"{'✅' if p.get('active') else '❌'} {p['name']}", f"adm_p_{uid}")]
            for uid,p in list(partners.items())[:15]]
    rows.append([_btn("➕ Add","adm_add_partner"), _btn("◀️ Back","adm_home")]); return _ik(*rows)

def kb_admin_sheets(sheets):
    rows = [[_btn(f"{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}", f"adm_s_{sid}")]
            for sid,s in list(sheets.items())[:15]]
    rows.append([_btn("➕ Add","adm_add_sheet"), _btn("◀️ Back","adm_home")]); return _ik(*rows)

def kb_platforms():
    rows = [[_btn(p["name"], f"plat_{k}")] for k,p in PLATFORMS.items()]
    rows.append([_btn("❌ Cancel","cancel")]); return _ik(*rows)

def kb_field_options(field_key, options):
    rows, row = [], []
    for opt in options:
        row.append(_btn(opt, f"fld_{field_key}__{opt}"))
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    return _ik(*rows)

def kb_oas():    return _ik([_btn("50%","fld_target_oas__50%"),_btn("55% ✦","fld_target_oas__55%"),_btn("60%","fld_target_oas__60%"),_btn("65%","fld_target_oas__65%")])
def kb_ftd():    return _ik([_btn("3","fld_min_ftd_gate__3"),_btn("5 ✦","fld_min_ftd_gate__5"),_btn("10","fld_min_ftd_gate__10")])
def kb_hr():     return _ik([_btn("1%","fld_hr_top_percent__1%"),_btn("2% ✦","fld_hr_top_percent__2%"),_btn("5%","fld_hr_top_percent__5%")])
def kb_confirm():return _ik([_btn("✅ Create","do_create"),_btn("❌ Cancel","cancel")])
def kb_partner_home(): return _ik([_btn("➕ Create New Sheet","p_create")],[_btn("📋 My Sheets","p_mysheets")])

def kb_select_mother(sheets):
    rows = [[_btn(f"{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}", f"p_mother_{s['id']}")] for s in sheets]
    rows.append([_btn("❌ Cancel","cancel")]); return _ik(*rows)

def kb_partner_sheets(kids):
    rows = [[_btn(f"{PLATFORMS.get(c.get('platform',''),{}).get('name','?')} — {c.get('created_at','')[:10]}", f"p_child_{c['spreadsheet_id']}")] for c in kids[-15:]]
    rows.append([_btn("◀️ Back","p_home")]); return _ik(*rows)

def kb_assign_sheets(partner, sheets):
    assigned = partner.get("assigned_sheet_ids",[])
    rows = []
    for sid,s in sheets.items():
        mark = "✅ " if sid in assigned else ""
        act  = f"unassign_{partner['telegram_id']}_{sid}" if sid in assigned else f"assign_{partner['telegram_id']}_{sid}"
        rows.append([_btn(f"{mark}{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}", act)])
    rows.append([_btn("◀️ Back", f"adm_p_{partner['telegram_id']}")])
    return _ik(*rows)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _next_step(platform_key, config):
    for step in WIZARD_STEPS:
        if step in PLATFORMS[platform_key]["fields"] and step not in config:
            return step
    return None

async def _send_step(target, state, platform_key, config, step):
    field = PLATFORMS[platform_key]["fields"][step]
    text  = f"⚙️ *{field['label']}*\nDefault: `{field.get('default','')}`"
    kb_map = {"target_oas": kb_oas, "min_ftd_gate": kb_ftd, "hr_top_percent": kb_hr}
    kb = kb_map.get(step, lambda: kb_field_options(step, field.get("options",[])))
    if isinstance(target, Message):
        await target.answer(text, parse_mode="Markdown", reply_markup=kb())
    else:
        await target.message.edit_text(text, parse_mode="Markdown", reply_markup=kb())
    await state.set_state(PartnerSt.config_step)


# ═══════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════

router  = Router()
storage: Storage   = None
gapi:    GoogleAPI = None


# ── common ────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(msg: Message):
    uid = msg.from_user.id
    if storage.is_admin(uid):
        await msg.answer("👑 Admin Panel", reply_markup=kb_admin_home())
    elif p := storage.get_partner(uid):
        if not p.get("active"): return await msg.answer("❌ Inactive. Contact admin.")
        await msg.answer(f"👋 Welcome, {p['name']}!", reply_markup=kb_partner_home())
    else:
        await msg.answer("You are not registered. Contact the admin.")

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if storage.is_admin(msg.from_user.id):
        await msg.answer("👑 Admin Panel", reply_markup=kb_admin_home())

@router.message(Command("testapi"))
async def cmd_testapi(msg: Message):
    if not storage.is_admin(msg.from_user.id): return

    # 1. Credentials type
    tok_exists = Path(TOKEN_FILE).exists()
    sa_exists  = Path(SERVICE_ACCOUNT_FILE).exists()
    mode = "OAuth (token.json)" if tok_exists else ("Service Account" if sa_exists else "NONE")
    await msg.answer(f"1️⃣ Credentials: `{mode}`", parse_mode="Markdown")

    try:
        creds = load_google_credentials()
        name  = getattr(creds, "service_account_email", None) or "OAuth user"
        await msg.answer(f"2️⃣ Auth: ✅ `{name}`", parse_mode="Markdown")
    except Exception as e:
        return await msg.answer(f"2️⃣ Auth: ❌\n`{e}`", parse_mode="Markdown")

    # 3. Create sheet via Drive
    created_id = None
    try:
        dr  = build("drive", "v3", credentials=creds)
        res = dr.files().create(
            body={"name": "_API_TEST_", "mimeType": "application/vnd.google-apps.spreadsheet"},
            fields="id,webViewLink",
        ).execute()
        created_id = res["id"]
        await msg.answer(f"3️⃣ Create Sheet: ✅\n`{created_id}`", parse_mode="Markdown")
    except Exception as e:
        await msg.answer(f"3️⃣ Create Sheet: ❌\n`{e}`", parse_mode="Markdown")

    # 4. Script API
    try:
        if created_id:
            sc = build("script", "v1", credentials=creds)
            sp = sc.projects().create(body={"title": "_TEST_", "parentId": created_id}).execute()
            await msg.answer(f"4️⃣ Script API: ✅\n`{sp['scriptId']}`", parse_mode="Markdown")
        else:
            await msg.answer("4️⃣ Script API: ⏭ skipped")
    except Exception as e:
        await msg.answer(f"4️⃣ Script API: ❌\n`{e}`", parse_mode="Markdown")

    if created_id:
        await msg.answer(f"🧹 Delete test sheet:\nhttps://docs.google.com/spreadsheets/d/{created_id}/edit")

@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = cb.from_user.id
    if storage.is_admin(uid):        await cb.message.edit_text("Cancelled.", reply_markup=kb_admin_home())
    elif storage.get_partner(uid):   await cb.message.edit_text("Cancelled.", reply_markup=kb_partner_home())
    else:                            await cb.message.edit_text("Cancelled.")
    await cb.answer()

# ── admin ─────────────────────────────────────────────────────

@router.callback_query(F.data == "adm_home")
async def cb_adm_home(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text("👑 Admin Panel", reply_markup=kb_admin_home()); await cb.answer()

@router.callback_query(F.data == "adm_partners")
async def cb_adm_partners(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    pp = storage.all_partners()
    await cb.message.edit_text(f"👥 Partners ({len(pp)})", reply_markup=kb_admin_partners(pp)); await cb.answer()

@router.callback_query(F.data == "adm_add_partner")
async def cb_adm_add_partner(cb: CallbackQuery, state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text("Enter partner's *Telegram ID*.\nForward their message to @userinfobot.", parse_mode="Markdown")
    await state.set_state(AdminSt.add_partner_id); await cb.answer()

@router.message(AdminSt.add_partner_id)
async def msg_partner_id(msg: Message, state: FSMContext):
    try: uid = int(msg.text.strip())
    except ValueError: return await msg.answer("❌ Must be a number:")
    await state.update_data(new_uid=uid)
    await msg.answer(f"ID: `{uid}`\n\nEnter a *name*:", parse_mode="Markdown")
    await state.set_state(AdminSt.add_partner_name)

@router.message(AdminSt.add_partner_name)
async def msg_partner_name(msg: Message, state: FSMContext):
    data = await state.get_data()
    name = msg.text.strip()
    storage.add_partner(data["new_uid"], name)
    await state.clear()
    await msg.answer(f"✅ Partner *{name}* added!", parse_mode="Markdown", reply_markup=kb_admin_home())

@router.callback_query(F.data.startswith("adm_p_"))
async def cb_view_partner(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    uid = int(cb.data.replace("adm_p_",""))
    p   = storage.get_partner(uid)
    if not p: return await cb.answer("Not found", show_alert=True)
    assigned    = storage.partner_assigned_sheets(uid)
    sheets_text = "\n".join(f"  • {s['name']}" for s in assigned) or "  (none)"
    await cb.message.edit_text(
        f"👤 *{p['name']}*\nID: `{uid}`\n"
        f"Status: {'✅ Active' if p.get('active') else '❌ Inactive'}\n"
        f"Child sheets: {len(p.get('child_sheets',[]))}\n\nAssigned:\n{sheets_text}",
        parse_mode="Markdown",
        reply_markup=_ik(
            [_btn("🔗 Assign/Remove Sheets", f"adm_assign_{uid}")],
            [_btn("❌ Deactivate" if p.get("active") else "✅ Activate", f"adm_toggle_{uid}")],
            [_btn("◀️ Back","adm_partners")],
        )
    ); await cb.answer()

@router.callback_query(F.data.startswith("adm_toggle_"))
async def cb_toggle(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    uid = int(cb.data.replace("adm_toggle_",""))
    p   = storage.get_partner(uid)
    if p: storage.update_partner(uid, {"active": not p.get("active",True)}); await cb.answer("Updated ✅")
    await cb_view_partner(cb)

@router.callback_query(F.data == "adm_sheets")
async def cb_adm_sheets(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    ss = storage.all_mother_sheets()
    await cb.message.edit_text(f"📋 Mother Sheets ({len(ss)})", reply_markup=kb_admin_sheets(ss)); await cb.answer()

@router.callback_query(F.data == "adm_add_sheet")
async def cb_add_sheet(cb: CallbackQuery, state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text("Enter *Spreadsheet ID*\n_(URL: …/spreadsheets/d/`[ID]`/edit)_", parse_mode="Markdown")
    await state.set_state(AdminSt.add_sheet_id); await cb.answer()

@router.message(AdminSt.add_sheet_id)
async def msg_sheet_id(msg: Message, state: FSMContext):
    await state.update_data(sheet_id=msg.text.strip())
    await msg.answer("Enter a *display name* (e.g. `Cellexpert Core`):", parse_mode="Markdown")
    await state.set_state(AdminSt.add_sheet_name)

@router.message(AdminSt.add_sheet_name)
async def msg_sheet_name(msg: Message, state: FSMContext):
    await state.update_data(sheet_name=msg.text.strip())
    await msg.answer("Enter *Apps Script Project ID*.\nscript.google.com → ⚙️ Project Settings → Script ID", parse_mode="Markdown")
    await state.set_state(AdminSt.add_script_id)

@router.message(AdminSt.add_script_id)
async def msg_script_id(msg: Message, state: FSMContext):
    await state.update_data(script_id=msg.text.strip())
    await msg.answer("Select *platform*:", parse_mode="Markdown", reply_markup=kb_platforms())
    await state.set_state(AdminSt.add_platform)

@router.callback_query(AdminSt.add_platform, F.data.startswith("plat_"))
async def cb_sheet_platform(cb: CallbackQuery, state: FSMContext):
    plat_key = cb.data.replace("plat_","")
    data     = await state.get_data()
    sheet    = storage.add_mother_sheet(data["sheet_id"], data["sheet_name"], data["script_id"], plat_key)
    await state.clear()
    await cb.message.edit_text(
        f"✅ *{sheet['name']}* added!\nPlatform: {PLATFORMS[plat_key]['name']}\nLibrary: `{sheet['library_symbol']}`",
        parse_mode="Markdown", reply_markup=kb_admin_home()); await cb.answer()

@router.callback_query(F.data.startswith("adm_s_"))
async def cb_view_sheet(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    sid = cb.data.replace("adm_s_",""); s = storage.get_mother_sheet(sid)
    if not s: return await cb.answer("Not found", show_alert=True)
    await cb.message.edit_text(
        f"📋 *{s['name']}*\nPlatform: {PLATFORMS.get(s['platform'],{}).get('name','?')}\n"
        f"Library: `{s['library_symbol']}`\nScript ID: `{s['script_id']}`",
        parse_mode="Markdown",
        reply_markup=_ik([_btn("🗑 Remove", f"adm_rmsheet_{sid}"), _btn("◀️ Back","adm_sheets")])); await cb.answer()

@router.callback_query(F.data.startswith("adm_rmsheet_"))
async def cb_rm_sheet(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    storage.remove_mother_sheet(cb.data.replace("adm_rmsheet_",""))
    await cb.answer("Removed"); await cb_adm_sheets(cb)

@router.callback_query(F.data == "adm_assign_sel")
async def cb_assign_sel(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    pp = storage.all_partners()
    if not pp: return await cb.answer("No partners yet", show_alert=True)
    rows = [[_btn(p["name"], f"adm_assign_{uid}")] for uid,p in pp.items()]
    rows.append([_btn("◀️ Back","adm_home")])
    await cb.message.edit_text("Select partner:", reply_markup=_ik(*rows)); await cb.answer()

@router.callback_query(F.data.startswith("adm_assign_"))
async def cb_assign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    uid = int(cb.data.replace("adm_assign_",""))
    p   = storage.get_partner(uid); ss = storage.all_mother_sheets()
    if not p or not ss: return await cb.answer("Nothing to assign", show_alert=True)
    await cb.message.edit_text(f"Toggle sheets for *{p['name']}* (✅ = assigned):", parse_mode="Markdown",
                                reply_markup=kb_assign_sheets(p, ss)); await cb.answer()

@router.callback_query(F.data.startswith("assign_"))
async def cb_do_assign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    _, uid_s, sid = cb.data.split("_",2)
    storage.assign_sheet(int(uid_s), sid); await cb.answer("Assigned ✅")
    cb.data = f"adm_assign_{uid_s}"; await cb_assign(cb)

@router.callback_query(F.data.startswith("unassign_"))
async def cb_do_unassign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    _, uid_s, sid = cb.data.split("_",2)
    storage.unassign_sheet(int(uid_s), sid); await cb.answer("Unassigned")
    cb.data = f"adm_assign_{uid_s}"; await cb_assign(cb)

# ── partner ───────────────────────────────────────────────────

@router.callback_query(F.data == "p_home")
async def cb_p_home(cb: CallbackQuery):
    p = storage.get_partner(cb.from_user.id)
    if not p: return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text(f"🏠 *{p['name']}*", parse_mode="Markdown", reply_markup=kb_partner_home()); await cb.answer()

@router.callback_query(F.data == "p_create")
async def cb_p_create(cb: CallbackQuery, state: FSMContext):
    p = storage.get_partner(cb.from_user.id)
    if not p or not p.get("active"): return await cb.answer("Account not active", show_alert=True)
    sheets = storage.partner_assigned_sheets(cb.from_user.id)
    if not sheets: return await cb.answer("No sheets assigned — contact admin", show_alert=True)
    await cb.message.edit_text("Select the *analytics platform*:", parse_mode="Markdown", reply_markup=kb_select_mother(sheets))
    await state.set_state(PartnerSt.pick_mother); await cb.answer()

@router.callback_query(PartnerSt.pick_mother, F.data.startswith("p_mother_"))
async def cb_pick_mother(cb: CallbackQuery, state: FSMContext):
    sid    = cb.data.replace("p_mother_",""); mother = storage.get_mother_sheet(sid)
    if not mother: return await cb.answer("Not found", show_alert=True)
    p = storage.get_partner(cb.from_user.id)
    if sid not in p.get("assigned_sheet_ids",[]): return await cb.answer("No access", show_alert=True)
    plat_key = mother["platform"]
    await state.update_data(mother_id=sid, platform_key=plat_key, config={})
    step = _next_step(plat_key, {})
    if step: await _send_step(cb, state, plat_key, {}, step)
    else:    await _show_confirm(cb, state)
    await cb.answer()

@router.callback_query(PartnerSt.config_step, F.data.startswith("fld_"))
async def cb_wizard(cb: CallbackQuery, state: FSMContext):
    raw = cb.data[4:]; sep = raw.index("__"); field = raw[:sep]; value = raw[sep+2:]
    data = await state.get_data(); config = data.get("config",{}); config[field] = value
    await state.update_data(config=config)
    nxt = _next_step(data["platform_key"], config)
    if nxt: await _send_step(cb, state, data["platform_key"], config, nxt)
    else:   await _show_confirm(cb, state)
    await cb.answer()

async def _show_confirm(cb, state):
    data   = await state.get_data(); config = data.get("config",{})
    mother = storage.get_mother_sheet(data["mother_id"]); plat = PLATFORMS[data["platform_key"]]
    lines  = "\n".join(f"  `{k}` → `{v}`" for k,v in config.items())
    await cb.message.edit_text(
        f"📋 *Confirm*\n\nPlatform: {plat['name']}\nSource: {mother['name']}\n"
        f"Library: `{plat['library_symbol']}`\n\n{lines}\n\nCreate?",
        parse_mode="Markdown", reply_markup=kb_confirm())
    await state.set_state(PartnerSt.confirm)

@router.callback_query(PartnerSt.confirm, F.data == "do_create")
async def cb_do_create(cb: CallbackQuery, state: FSMContext):
    data   = await state.get_data(); p = storage.get_partner(cb.from_user.id)
    mother = storage.get_mother_sheet(data["mother_id"]); plat = PLATFORMS[data["platform_key"]]
    await cb.message.edit_text("⏳ Creating spreadsheet… (~30–60 sec)"); await cb.answer()
    try:
        child = await asyncio.to_thread(gapi.create_child_sheet,
                                        partner_name=p["name"], platform_key=data["platform_key"], mother=mother)
        storage.add_child_sheet(cb.from_user.id, child)
        await cb.message.edit_text(
            f"✅ *Sheet ready!*\n\n🔗 [Open Spreadsheet]({child['spreadsheet_url']})\n\n"
            f"Platform: {plat['name']}\nLibrary: `{plat['library_symbol']}`\n\n"
            f"_Paste raw data → Raw Data tab → run 📊 ANALYSIS_",
            parse_mode="Markdown", reply_markup=kb_partner_home())
    except Exception as exc:
        log.exception("create_child_sheet failed")
        await cb.message.edit_text(f"❌ Failed.\n\n`{str(exc)[:400]}`\n\nContact admin.",
                                   parse_mode="Markdown", reply_markup=kb_partner_home())
    await state.clear()

@router.callback_query(F.data == "p_mysheets")
async def cb_mysheets(cb: CallbackQuery):
    p = storage.get_partner(cb.from_user.id)
    if not p: return await cb.answer("No access", show_alert=True)
    kids = p.get("child_sheets",[])
    if not kids: await cb.message.edit_text("No sheets yet.", reply_markup=kb_partner_home())
    else: await cb.message.edit_text(f"📋 *Your Sheets* ({len(kids)})", parse_mode="Markdown", reply_markup=kb_partner_sheets(kids))
    await cb.answer()

@router.callback_query(F.data.startswith("p_child_"))
async def cb_view_child(cb: CallbackQuery):
    sid = cb.data.replace("p_child_",""); p = storage.get_partner(cb.from_user.id)
    c   = next((x for x in p.get("child_sheets",[]) if x["spreadsheet_id"]==sid), None)
    if not c: return await cb.answer("Not found", show_alert=True)
    plat = PLATFORMS.get(c.get("platform",""),{})
    await cb.message.edit_text(
        f"📊 *{plat.get('name','?')}*\nCreated: {c.get('created_at','')[:10]}\n\n🔗 [Open]({c['spreadsheet_url']})",
        parse_mode="Markdown", reply_markup=_ik([_btn("◀️ Back","p_mysheets")])); await cb.answer()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

async def main():
    global storage, gapi
    assert BOT_TOKEN, "BOT_TOKEN env var is not set"
    storage = Storage(DATA_FILE)
    gapi    = GoogleAPI()
    if FIRST_ADMIN_ID: storage.add_admin(FIRST_ADMIN_ID)
    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    log.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message","callback_query"])

if __name__ == "__main__":
    asyncio.run(main())
