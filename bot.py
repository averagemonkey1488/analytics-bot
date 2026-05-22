#!/usr/bin/env python3
"""
TD Analytics Toolkit Bot
Telegram bot for managing affiliate analytics spreadsheets.

Supports platforms: Cellexpert (ChinCore), ReferOn (TDCore),
                    Affilka Standard (TDCoreV5), Affilka FB (FBCore)

Flow:
  Admin → registers partners, adds mother sheets, assigns access
  Partner → creates child sheets pre-loaded with library + config
"""

import asyncio
import json
import logging
import os
# --- Railway: load service account from env var ---
_sa_json = os.getenv("SERVICE_ACCOUNT_JSON")
if _sa_json:
    with open("service_account.json", "w") as _f:
        _f.write(_sa_json)
# ---------------------------------------------------
from datetime import datetime
from pathlib import Path
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message,
)
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# ENV / CONSTANTS
# ═══════════════════════════════════════════════════════════════

from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN            = os.getenv("BOT_TOKEN", "")
SERVICE_ACCOUNT_FILE = os.getenv("SERVICE_ACCOUNT_FILE", "service_account.json")
DATA_FILE            = os.getenv("DATA_FILE", "data.json")
FIRST_ADMIN_ID       = int(os.getenv("FIRST_ADMIN_ID", "0"))

GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/script.projects",
]

# ═══════════════════════════════════════════════════════════════
# PLATFORM DEFINITIONS
# Every platform maps to a mother-sheet script library.
# ═══════════════════════════════════════════════════════════════

PLATFORMS: dict = {
    "cellexpert": {
        "name": "🎯 Cellexpert",
        "library_symbol": "ChinCore",
        "fields": {
            "webname": {
                "label": "Webname field",
                "default": "afp2",
                "options": ["afp1", "afp2", "afp3", "afp4", "afp6", "afp10"],
            },
            "creo": {
                "label": "Creo field",
                "default": "afp6",
                "options": ["afp1", "afp2", "afp3", "afp4", "afp6", "afp10"],
            },
            "clickid": {
                "label": "Click ID field",
                "default": "afp1",
                "options": ["afp1", "afp2", "afp3", "afp4", "afp6", "afp10"],
            },
            "target_oas":     {"label": "Target OAS",     "default": "55%"},
            "hr_top_percent": {"label": "HR Top %",        "default": "2%"},
        },
        "public_api": {
            "quality":    "processFullReportBoth_Public",
            "oas":        "buildOASByWebBoth_Public",
            "export":     "exportWebnameReports_Public",
            "root_index": "openRootIndex_Public",
            "ex_config":  "createExportConfig_Public",
            "debug_map":  "debugExportMapping_Public",
            "stop":       "stopExport_Public",
            "reset":      "hardResetExportCache_Public",
            "chunk":      "EX_exportChunk_Public",
            "ping":       "ChinCore_ping_Public",
        },
    },
    "referon": {
        "name": "📊 ReferOn",
        "library_symbol": "TDCore",
        "fields": {
            "webname": {
                "label": "Webname field",
                "default": "pubid",
                "options": ["pubid", "subid", "var1", "var2", "var3", "var4", "var5", "clickid"],
            },
            "creo": {
                "label": "Creo field",
                "default": "var3",
                "options": ["var1", "var2", "var3", "var4", "var5", "pubid", "subid"],
            },
            "clickid": {
                "label": "Click ID field",
                "default": "clickid",
                "options": ["clickid", "click_id", "var1", "var2", "var3", "var4", "var5"],
            },
            "target_oas":  {"label": "Target OAS",   "default": "55%"},
            "min_ftd_gate":{"label": "Min FTD Gate", "default": "5"},
        },
        "public_api": {
            "quality":    "processAllPrograms_Public",
            "oas":        "buildOASByWeb_Public",
            "export":     "exportFeedsByRealWebname_Public",
            "root_index": "openRootIndex_Public",
            "ex_config":  "openExportConfig_Public",
            "debug_map":  "debugExportMapping_Public",
            "stop":       "stopExportAndReset_Public",
            "reset":      "resetCache_Public",
            "chunk":      "EX_exportChunk_Public",
            "ping":       "CPCore_ping_Public",
        },
    },
    "affilka_fb": {
        "name": "📱 Affilka FB",
        "library_symbol": "FBCore",
        "fields": {
            "webname": {
                "label": "Webname field",
                "default": "afp1",
                "options": ["afp1", "afp2", "afp3", "afp4", "afp10", "promo_code", "promo_name"],
            },
            "creo": {
                "label": "Creo field",
                "default": "afp1",
                "options": ["afp1", "afp2", "afp3", "afp4", "afp10", "promo_code", "promo_name"],
            },
            "clickid": {
                "label": "Click ID field",
                "default": "afp3",
                "options": ["afp1", "afp2", "afp3", "afp4", "afp10"],
            },
            "target_oas":     {"label": "Target OAS",  "default": "55%"},
            "hr_top_percent": {"label": "HR Top %",    "default": "2%"},
            "min_ftd_gate":   {"label": "Min FTD Gate","default": "5"},
        },
        "public_api": {
            "quality":    "processAllPrograms_Public",
            "oas":        "buildOASByWeb_Public",
            "export":     "exportFeedsByRealWebname_Public",
            "root_index": "openRootIndex_Public",
            "ex_config":  "openExportConfig_Public",
            "debug_map":  "debugExportMapping_Public",
            "normalize":  "normalizeRawData_Public",
            "debug_raw":  "debugRawValues_Public",
            "stop":       "stopExportAndReset_Public",
            "reset":      "resetCache_Public",
            "chunk":      "EX_exportChunk_Public",
            "ping":       "CPCore_ping_Public",
        },
    },
    "affilka": {
        "name": "🔗 Affilka Standard",
        "library_symbol": "TDCoreV5",
        "fields": {
            "webname": {
                "label": "Webname field",
                "default": "pubid",
                "options": ["pubid", "subid", "var1", "var2", "var3", "var4", "var5"],
            },
            "creo": {
                "label": "Creo field",
                "default": "var3",
                "options": ["var1", "var2", "var3", "var4", "var5", "pubid"],
            },
            "clickid": {
                "label": "Click ID field",
                "default": "clickid",
                "options": ["clickid", "var1", "var2", "var3", "var4", "var5"],
            },
            "target_oas":  {"label": "Target OAS",   "default": "55%"},
            "min_ftd_gate":{"label": "Min FTD Gate", "default": "5"},
        },
        "public_api": {
            "quality":    "processAllPrograms_Public",
            "oas":        "buildOASByWeb_Public",
            "export":     "exportFeedsByRealWebname_Public",
            "root_index": "openRootIndex_Public",
            "ex_config":  "openExportConfig_Public",
            "debug_map":  "debugExportMapping_Public",
            "stop":       "stopExportAndReset_Public",
            "reset":      "resetCache_Public",
            "chunk":      "EX_exportChunk_Public",
            "ping":       "CPCore_ping_Public",
        },
    },
}

# Config wizard step order (fields shown in sequence)
WIZARD_STEPS = ["webname", "creo", "clickid", "target_oas", "min_ftd_gate", "hr_top_percent"]

# ═══════════════════════════════════════════════════════════════
# GAS SCRIPT GENERATOR
# Builds the loader .gs file that gets injected into each child sheet.
# ═══════════════════════════════════════════════════════════════

def build_loader_script(platform_key: str) -> str:
    """Return the Google Apps Script loader code for the given platform."""
    p   = PLATFORMS[platform_key]
    sym = p["library_symbol"]
    api = p["public_api"]

    # --- onOpen menu ---
    analysis_items = [
        f"    .addItem('📈 Quality Tracking', '_runQuality')",
        f"    .addItem('🎯 OAS Tracking',      '_runOAS')",
        "    .addSeparator()",
        f"    .addItem('📦 Webname Export',    '_runExport')",
        f"    .addItem('🗂 Open Root Index',   '_runRootIndex')",
    ]
    if platform_key == "affilka_fb":
        analysis_items += [
            "    .addSeparator()",
            "    .addItem('🔧 Normalize Raw Data', '_runNormalize')",
        ]

    tech_items = [
        f"    .addItem('⚙️ Export Config',       '_runExConfig')",
        f"    .addItem('🔍 Debug Export Mapping', '_runDebugMap')",
    ]
    if platform_key == "affilka_fb":
        tech_items.append("    .addItem('🔢 Debug Raw Values',    '_runDebugRaw')")
    tech_items += [
        "    .addSeparator()",
        f"    .addItem('🛑 Stop / Reset Export', '_runStop')",
        "    .addSeparator()",
        f"    .addItem('💥 HARD Reset Cache',    '_runReset')",
        "    .addSeparator()",
        f"    .addItem('✅ Test Connection',     '_runPing')",
    ]

    # --- wrapper functions ---
    def fn(name: str, call: str) -> str:
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
        fns.append(fn("_runNormalize", api["normalize"]))
        fns.append(fn("_runDebugRaw",  api["debug_raw"]))

    fns.append(
        f"function _runPing() {{\n"
        f"  var r = {sym}.{api['ping']}();\n"
        f"  SpreadsheetApp.getUi().alert(r);\n"
        f"}}"
    )

    return (
        f"// Auto-generated loader — {p['name']} — {datetime.utcnow():%Y-%m-%d %H:%M} UTC\n"
        f"// Library: {sym}\n\n"
        f"function onOpen() {{\n"
        f"  var ui = SpreadsheetApp.getUi();\n"
        f"  ui.createMenu('📊 ANALYSIS')\n"
        f"{chr(10).join(analysis_items)}\n"
        f"    .addToUi();\n"
        f"  ui.createMenu('🛠 TECH PANEL')\n"
        f"{chr(10).join(tech_items)}\n"
        f"    .addToUi();\n"
        f"}}\n\n"
        + "\n".join(fns)
    )


def build_manifest(library_symbol: str, script_id: str) -> str:
    """Return appsscript.json manifest with the library reference."""
    return json.dumps(
        {
            "timeZone": "Europe/London",
            "dependencies": {
                "libraries": [
                    {
                        "userSymbol": library_symbol,
                        "scriptId": script_id,
                        "version": "0",
                        "developmentMode": True,
                    }
                ]
            },
            "exceptionLogging": "STACKDRIVER",
            "runtimeVersion": "V8",
        },
        indent=2,
    )


# ═══════════════════════════════════════════════════════════════
# STORAGE  (JSON file — swap for SQLite/Postgres in production)
# ═══════════════════════════════════════════════════════════════

class Storage:
    def __init__(self, path: str):
        self._path = path
        self._d = self._load()

    def _load(self) -> dict:
        if Path(self._path).exists():
            with open(self._path, encoding="utf-8") as f:
                return json.load(f)
        return {"admins": [], "mother_sheets": {}, "partners": {}}

    def _save(self):
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump(self._d, f, indent=2, ensure_ascii=False)

    # ── admins ──────────────────────────────────────────────────

    def is_admin(self, uid: int) -> bool:
        return uid in self._d["admins"]

    def add_admin(self, uid: int):
        if uid and uid not in self._d["admins"]:
            self._d["admins"].append(uid)
            self._save()

    # ── mother sheets ───────────────────────────────────────────

    def add_mother_sheet(self, sheet_id: str, name: str,
                         script_id: str, platform: str) -> dict:
        entry = {
            "id": sheet_id,
            "name": name,
            "script_id": script_id,
            "platform": platform,
            "library_symbol": PLATFORMS[platform]["library_symbol"],
            "created_at": datetime.utcnow().isoformat(),
        }
        self._d["mother_sheets"][sheet_id] = entry
        self._save()
        return entry

    def get_mother_sheet(self, sid: str) -> Optional[dict]:
        return self._d["mother_sheets"].get(sid)

    def all_mother_sheets(self) -> dict:
        return self._d["mother_sheets"]

    def remove_mother_sheet(self, sid: str):
        self._d["mother_sheets"].pop(sid, None)
        self._save()

    # ── partners ────────────────────────────────────────────────

    def add_partner(self, uid: int, name: str, username: str = "") -> dict:
        entry = {
            "telegram_id": uid,
            "name": name,
            "username": username,
            "assigned_sheet_ids": [],
            "child_sheets": [],
            "active": True,
            "created_at": datetime.utcnow().isoformat(),
        }
        self._d["partners"][str(uid)] = entry
        self._save()
        return entry

    def get_partner(self, uid: int) -> Optional[dict]:
        return self._d["partners"].get(str(uid))

    def all_partners(self) -> dict:
        return self._d["partners"]

    def update_partner(self, uid: int, patch: dict):
        p = self.get_partner(uid)
        if p:
            p.update(patch)
            self._d["partners"][str(uid)] = p
            self._save()

    def assign_sheet(self, uid: int, sid: str):
        p = self.get_partner(uid)
        if p and sid not in p["assigned_sheet_ids"]:
            p["assigned_sheet_ids"].append(sid)
            self._save()

    def unassign_sheet(self, uid: int, sid: str):
        p = self.get_partner(uid)
        if p and sid in p["assigned_sheet_ids"]:
            p["assigned_sheet_ids"].remove(sid)
            self._save()

    def add_child_sheet(self, uid: int, child: dict):
        p = self.get_partner(uid)
        if p:
            p["child_sheets"].append(child)
            self._save()

    def partner_assigned_sheets(self, uid: int) -> list[dict]:
        p = self.get_partner(uid)
        if not p:
            return []
        return [self.get_mother_sheet(s) for s in p["assigned_sheet_ids"] if self.get_mother_sheet(s)]


# ═══════════════════════════════════════════════════════════════
# GOOGLE API  (sync calls wrapped in asyncio.to_thread)
# ═══════════════════════════════════════════════════════════════

class GoogleAPI:
    def __init__(self, sa_file: str):
        creds = Credentials.from_service_account_file(sa_file, scopes=GOOGLE_SCOPES)
        self._sheets = build("sheets", "v4", credentials=creds)
        self._drive  = build("drive",  "v3", credentials=creds)
        self._script = build("script", "v1", credentials=creds)

    # ── spreadsheet ─────────────────────────────────────────────

    def _create_spreadsheet(self, title: str) -> dict:
        res = self._sheets.spreadsheets().create(
            body={"properties": {"title": title}}
        ).execute()
        return {"id": res["spreadsheetId"], "url": res["spreadsheetUrl"]}

    def _share_anyone_write(self, file_id: str):
        self._drive.permissions().create(
            fileId=file_id,
            body={"type": "anyone", "role": "writer"},
            fields="id",
        ).execute()

    # ── apps script ─────────────────────────────────────────────

    def _create_bound_script(self, spreadsheet_id: str, title: str) -> str:
        res = self._script.projects().create(
            body={"title": title, "parentId": spreadsheet_id}
        ).execute()
        return res["scriptId"]

    def _push_script_files(self, script_id: str, loader_js: str, manifest_json: str):
        self._script.projects().updateContent(
            scriptId=script_id,
            body={
                "files": [
                    {"name": "appsscript", "type": "JSON",      "source": manifest_json},
                    {"name": "Loader",     "type": "SERVER_JS", "source": loader_js},
                ]
            },
        ).execute()

    # ── full flow (called via asyncio.to_thread) ─────────────────

    def create_child_sheet(self, partner_name: str, platform_key: str,
                           mother: dict) -> dict:
        plat  = PLATFORMS[platform_key]
        title = f"{partner_name} — {plat['name']} Analytics"

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
    add_partner_id   = State()
    add_partner_name = State()
    add_sheet_id     = State()
    add_sheet_name   = State()
    add_script_id    = State()
    add_platform     = State()


class PartnerSt(StatesGroup):
    pick_mother  = State()
    config_step  = State()   # iterates through WIZARD_STEPS
    confirm      = State()


# ═══════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════

def _ik(*rows) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))

def _btn(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=data)

def kb_admin_home() -> InlineKeyboardMarkup:
    return _ik(
        [_btn("👥 Partners",       "adm_partners"),  _btn("📋 Mother Sheets", "adm_sheets")],
        [_btn("🔗 Assign Sheets",  "adm_assign_sel")],
    )

def kb_admin_partners(partners: dict) -> InlineKeyboardMarkup:
    rows = [[_btn(
        f"{'✅' if p.get('active') else '❌'} {p['name']} (@{p.get('username','?')})",
        f"adm_p_{uid}"
    )] for uid, p in list(partners.items())[:15]]
    rows.append([_btn("➕ Add", "adm_add_partner"), _btn("◀️ Back", "adm_home")])
    return _ik(*rows)

def kb_admin_sheets(sheets: dict) -> InlineKeyboardMarkup:
    rows = [[_btn(
        f"{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}",
        f"adm_s_{sid}"
    )] for sid, s in list(sheets.items())[:15]]
    rows.append([_btn("➕ Add", "adm_add_sheet"), _btn("◀️ Back", "adm_home")])
    return _ik(*rows)

def kb_platforms() -> InlineKeyboardMarkup:
    rows = [[_btn(p["name"], f"plat_{k}")] for k, p in PLATFORMS.items()]
    rows.append([_btn("❌ Cancel", "cancel")])
    return _ik(*rows)

def kb_field_options(field_key: str, options: list) -> InlineKeyboardMarkup:
    rows, row = [], []
    for opt in options:
        row.append(_btn(opt, f"fld_{field_key}__{opt}"))
        if len(row) == 3:
            rows.append(row); row = []
    if row:
        rows.append(row)
    return _ik(*rows)

def kb_oas_options() -> InlineKeyboardMarkup:
    return _ik([_btn("50%", "fld_target_oas__50%"),
                _btn("55% ✦", "fld_target_oas__55%"),
                _btn("60%", "fld_target_oas__60%"),
                _btn("65%", "fld_target_oas__65%")])

def kb_minftd_options() -> InlineKeyboardMarkup:
    return _ik([_btn("3", "fld_min_ftd_gate__3"),
                _btn("5 ✦", "fld_min_ftd_gate__5"),
                _btn("10", "fld_min_ftd_gate__10")])

def kb_hr_options() -> InlineKeyboardMarkup:
    return _ik([_btn("1%", "fld_hr_top_percent__1%"),
                _btn("2% ✦", "fld_hr_top_percent__2%"),
                _btn("5%", "fld_hr_top_percent__5%")])

def kb_confirm_create() -> InlineKeyboardMarkup:
    return _ik([_btn("✅ Create", "do_create"), _btn("❌ Cancel", "cancel")])

def kb_partner_home() -> InlineKeyboardMarkup:
    return _ik([_btn("➕ Create New Sheet", "p_create")],
               [_btn("📋 My Sheets",        "p_mysheets")])

def kb_select_mother(sheets: list) -> InlineKeyboardMarkup:
    rows = [[_btn(
        f"{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}",
        f"p_mother_{s['id']}"
    )] for s in sheets]
    rows.append([_btn("❌ Cancel", "cancel")])
    return _ik(*rows)

def kb_partner_sheets(child_sheets: list) -> InlineKeyboardMarkup:
    rows = [[_btn(
        f"{PLATFORMS.get(c.get('platform',''),{}).get('name','?')} — {c.get('created_at','')[:10]}",
        f"p_child_{c['spreadsheet_id']}"
    )] for c in child_sheets[-15:]]
    rows.append([_btn("◀️ Back", "p_home")])
    return _ik(*rows)

def kb_assign_sheets(partner: dict, sheets: dict) -> InlineKeyboardMarkup:
    assigned = partner.get("assigned_sheet_ids", [])
    rows = []
    for sid, s in sheets.items():
        mark = "✅ " if sid in assigned else ""
        act  = f"unassign_{partner['telegram_id']}_{sid}" if sid in assigned \
               else f"assign_{partner['telegram_id']}_{sid}"
        rows.append([_btn(
            f"{mark}{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}", act
        )])
    rows.append([_btn("◀️ Back", f"adm_p_{partner['telegram_id']}")])
    return _ik(*rows)


# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════

def _next_wizard_step(platform_key: str, config: dict) -> Optional[str]:
    """Return the next field key that still needs to be filled."""
    fields = PLATFORMS[platform_key]["fields"]
    for step in WIZARD_STEPS:
        if step in fields and step not in config:
            return step
    return None


async def _send_wizard_step(target, state: FSMContext,
                             platform_key: str, config: dict,
                             step: str):
    """Send the prompt for a wizard step (works for both Message and CallbackQuery)."""
    field  = PLATFORMS[platform_key]["fields"][step]
    label  = field["label"]
    dflt   = field.get("default", "")
    opts   = field.get("options", [])

    text = f"⚙️ *{label}*\nDefault: `{dflt}`"

    if step == "target_oas":
        kb = kb_oas_options()
    elif step == "min_ftd_gate":
        kb = kb_minftd_options()
    elif step == "hr_top_percent":
        kb = kb_hr_options()
    else:
        kb = kb_field_options(step, opts)

    if isinstance(target, Message):
        await target.answer(text, parse_mode="Markdown", reply_markup=kb)
    else:
        await target.message.edit_text(text, parse_mode="Markdown", reply_markup=kb)

    await state.set_state(PartnerSt.config_step)


# ═══════════════════════════════════════════════════════════════
# ROUTER + GLOBAL SINGLETONS
# ═══════════════════════════════════════════════════════════════

router   = Router()
storage: Storage   = None   # type: ignore[assignment]
gapi:    GoogleAPI = None   # type: ignore[assignment]


# ═══════════════════════════════════════════════════════════════
# HANDLERS — COMMON
# ═══════════════════════════════════════════════════════════════

@router.message(CommandStart())
async def cmd_start(msg: Message):
    uid = msg.from_user.id
    if storage.is_admin(uid):
        await msg.answer("👑 Admin Panel", reply_markup=kb_admin_home())
    elif p := storage.get_partner(uid):
        if not p.get("active"):
            await msg.answer("❌ Your account is inactive. Contact admin.")
            return
        await msg.answer(f"👋 Welcome, {p['name']}!", reply_markup=kb_partner_home())
    else:
        await msg.answer("You are not registered. Contact the admin for access.")


@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if storage.is_admin(msg.from_user.id):
        await msg.answer("👑 Admin Panel", reply_markup=kb_admin_home())


@router.callback_query(F.data == "cancel")
async def cb_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    uid = cb.from_user.id
    if storage.is_admin(uid):
        await cb.message.edit_text("Cancelled.", reply_markup=kb_admin_home())
    elif storage.get_partner(uid):
        await cb.message.edit_text("Cancelled.", reply_markup=kb_partner_home())
    else:
        await cb.message.edit_text("Cancelled.")
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
# HANDLERS — ADMIN HOME
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "adm_home")
async def cb_adm_home(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text("👑 Admin Panel", reply_markup=kb_admin_home())
    await cb.answer()


# ─── Partners list ────────────────────────────────────────────

@router.callback_query(F.data == "adm_partners")
async def cb_adm_partners(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    pp = storage.all_partners()
    await cb.message.edit_text(f"👥 Partners ({len(pp)})", reply_markup=kb_admin_partners(pp))
    await cb.answer()


@router.callback_query(F.data == "adm_add_partner")
async def cb_adm_add_partner(cb: CallbackQuery, state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text(
        "Enter the partner's *Telegram ID* (numeric).\n"
        "Forward their message to @userinfobot to get it.",
        parse_mode="Markdown",
    )
    await state.set_state(AdminSt.add_partner_id)
    await cb.answer()


@router.message(AdminSt.add_partner_id)
async def msg_adm_partner_id(msg: Message, state: FSMContext):
    try:
        uid = int(msg.text.strip())
    except ValueError:
        return await msg.answer("❌ Must be a number. Try again:")
    await state.update_data(new_uid=uid)
    await msg.answer(f"ID: `{uid}`\n\nNow enter a *name* for this partner:", parse_mode="Markdown")
    await state.set_state(AdminSt.add_partner_name)


@router.message(AdminSt.add_partner_name)
async def msg_adm_partner_name(msg: Message, state: FSMContext):
    data = await state.get_data()
    uid  = data["new_uid"]
    name = msg.text.strip()
    storage.add_partner(uid, name)
    await state.clear()
    await msg.answer(
        f"✅ Partner *{name}* (`{uid}`) added.\n\n"
        f"Assign mother sheets via Admin → Assign Sheets.",
        parse_mode="Markdown",
        reply_markup=kb_admin_home(),
    )


@router.callback_query(F.data.startswith("adm_p_"))
async def cb_adm_view_partner(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    uid = int(cb.data.replace("adm_p_", ""))
    p   = storage.get_partner(uid)
    if not p: return await cb.answer("Not found", show_alert=True)
    assigned = storage.partner_assigned_sheets(uid)
    sheets_text = "\n".join(f"  • {s['name']}" for s in assigned) or "  (none)"
    status = "✅ Active" if p.get("active") else "❌ Inactive"
    text = (
        f"👤 *{p['name']}*\n"
        f"ID: `{uid}` | @{p.get('username','?')}\n"
        f"Status: {status}\n"
        f"Child sheets: {len(p.get('child_sheets', []))}\n\n"
        f"Assigned mother sheets:\n{sheets_text}"
    )
    toggle_label = "❌ Deactivate" if p.get("active") else "✅ Activate"
    await cb.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=_ik(
            [_btn("🔗 Assign/Remove Sheets", f"adm_assign_{uid}")],
            [_btn(toggle_label, f"adm_toggle_{uid}")],
            [_btn("◀️ Back", "adm_partners")],
        ),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm_toggle_"))
async def cb_adm_toggle(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    uid = int(cb.data.replace("adm_toggle_", ""))
    p   = storage.get_partner(uid)
    if p:
        storage.update_partner(uid, {"active": not p.get("active", True)})
        await cb.answer("Status updated ✅")
        await cb_adm_view_partner(cb)  # refresh


# ─── Mother sheets list ───────────────────────────────────────

@router.callback_query(F.data == "adm_sheets")
async def cb_adm_sheets(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    ss = storage.all_mother_sheets()
    await cb.message.edit_text(f"📋 Mother Sheets ({len(ss)})", reply_markup=kb_admin_sheets(ss))
    await cb.answer()


@router.callback_query(F.data == "adm_add_sheet")
async def cb_adm_add_sheet(cb: CallbackQuery, state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text(
        "Enter the *Google Spreadsheet ID* of the mother sheet.\n"
        "_(from URL: …/spreadsheets/d/`[ID]`/edit)_",
        parse_mode="Markdown",
    )
    await state.set_state(AdminSt.add_sheet_id)
    await cb.answer()


@router.message(AdminSt.add_sheet_id)
async def msg_adm_sheet_id(msg: Message, state: FSMContext):
    await state.update_data(sheet_id=msg.text.strip())
    await msg.answer("Enter a short *display name* for this sheet (e.g. `Cellexpert Core`):",
                     parse_mode="Markdown")
    await state.set_state(AdminSt.add_sheet_name)


@router.message(AdminSt.add_sheet_name)
async def msg_adm_sheet_name(msg: Message, state: FSMContext):
    await state.update_data(sheet_name=msg.text.strip())
    await msg.answer(
        "Enter the *Apps Script Project ID* (the library script).\n"
        "script.google.com → project → ⚙️ Project Settings → *Script ID*",
        parse_mode="Markdown",
    )
    await state.set_state(AdminSt.add_script_id)


@router.message(AdminSt.add_script_id)
async def msg_adm_script_id(msg: Message, state: FSMContext):
    await state.update_data(script_id=msg.text.strip())
    await msg.answer("Select the *platform type* for this sheet:", parse_mode="Markdown",
                     reply_markup=kb_platforms())
    await state.set_state(AdminSt.add_platform)


@router.callback_query(AdminSt.add_platform, F.data.startswith("plat_"))
async def cb_adm_sheet_platform(cb: CallbackQuery, state: FSMContext):
    plat_key = cb.data.replace("plat_", "")
    data = await state.get_data()
    sheet = storage.add_mother_sheet(
        sheet_id=data["sheet_id"],
        name=data["sheet_name"],
        script_id=data["script_id"],
        platform=plat_key,
    )
    await state.clear()
    await cb.message.edit_text(
        f"✅ Mother sheet *{sheet['name']}* added!\n"
        f"Platform: {PLATFORMS[plat_key]['name']}\n"
        f"Library: `{sheet['library_symbol']}`",
        parse_mode="Markdown",
        reply_markup=kb_admin_home(),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm_s_"))
async def cb_adm_view_sheet(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    sid = cb.data.replace("adm_s_", "")
    s   = storage.get_mother_sheet(sid)
    if not s: return await cb.answer("Not found", show_alert=True)
    await cb.message.edit_text(
        f"📋 *{s['name']}*\n"
        f"Platform: {PLATFORMS.get(s['platform'],{}).get('name','?')}\n"
        f"Library: `{s['library_symbol']}`\n"
        f"Script ID: `{s['script_id']}`\n"
        f"Sheet ID: `{s['id']}`",
        parse_mode="Markdown",
        reply_markup=_ik(
            [_btn("🗑 Remove", f"adm_rmsheet_{sid}"), _btn("◀️ Back", "adm_sheets")]
        ),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("adm_rmsheet_"))
async def cb_adm_remove_sheet(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    sid = cb.data.replace("adm_rmsheet_", "")
    storage.remove_mother_sheet(sid)
    await cb.answer("Sheet removed")
    await cb_adm_sheets(cb)


# ─── Assign sheets ────────────────────────────────────────────

@router.callback_query(F.data == "adm_assign_sel")
async def cb_adm_assign_sel(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    pp = storage.all_partners()
    if not pp:
        return await cb.answer("No partners yet", show_alert=True)
    rows = [[_btn(p["name"], f"adm_assign_{uid}")] for uid, p in pp.items()]
    rows.append([_btn("◀️ Back", "adm_home")])
    await cb.message.edit_text("Select a partner:", reply_markup=_ik(*rows))
    await cb.answer()


@router.callback_query(F.data.startswith("adm_assign_"))
async def cb_adm_assign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    uid = int(cb.data.replace("adm_assign_", ""))
    p   = storage.get_partner(uid)
    ss  = storage.all_mother_sheets()
    if not p or not ss:
        return await cb.answer("Nothing to assign", show_alert=True)
    await cb.message.edit_text(
        f"Toggle sheets for *{p['name']}* (✅ = assigned):",
        parse_mode="Markdown",
        reply_markup=kb_assign_sheets(p, ss),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("assign_"))
async def cb_do_assign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    _, uid_s, sid = cb.data.split("_", 2)
    storage.assign_sheet(int(uid_s), sid)
    await cb.answer("Assigned ✅")
    # refresh
    cb.data = f"adm_assign_{uid_s}"
    await cb_adm_assign(cb)


@router.callback_query(F.data.startswith("unassign_"))
async def cb_do_unassign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access", show_alert=True)
    _, uid_s, sid = cb.data.split("_", 2)
    storage.unassign_sheet(int(uid_s), sid)
    await cb.answer("Unassigned")
    cb.data = f"adm_assign_{uid_s}"
    await cb_adm_assign(cb)


# ═══════════════════════════════════════════════════════════════
# HANDLERS — PARTNER
# ═══════════════════════════════════════════════════════════════

@router.callback_query(F.data == "p_home")
async def cb_p_home(cb: CallbackQuery):
    p = storage.get_partner(cb.from_user.id)
    if not p: return await cb.answer("No access", show_alert=True)
    await cb.message.edit_text(f"🏠 *{p['name']}*", parse_mode="Markdown",
                                reply_markup=kb_partner_home())
    await cb.answer()


@router.callback_query(F.data == "p_create")
async def cb_p_create(cb: CallbackQuery, state: FSMContext):
    p = storage.get_partner(cb.from_user.id)
    if not p or not p.get("active"):
        return await cb.answer("Account not active", show_alert=True)
    sheets = storage.partner_assigned_sheets(cb.from_user.id)
    if not sheets:
        return await cb.answer("No sheets assigned to you yet — contact admin", show_alert=True)
    await cb.message.edit_text(
        "Select the *analytics platform* for the new sheet:",
        parse_mode="Markdown",
        reply_markup=kb_select_mother(sheets),
    )
    await state.set_state(PartnerSt.pick_mother)
    await cb.answer()


@router.callback_query(PartnerSt.pick_mother, F.data.startswith("p_mother_"))
async def cb_pick_mother(cb: CallbackQuery, state: FSMContext):
    sid    = cb.data.replace("p_mother_", "")
    mother = storage.get_mother_sheet(sid)
    if not mother: return await cb.answer("Not found", show_alert=True)

    p = storage.get_partner(cb.from_user.id)
    if sid not in p.get("assigned_sheet_ids", []):
        return await cb.answer("No access to this sheet", show_alert=True)

    plat_key = mother["platform"]
    await state.update_data(mother_id=sid, platform_key=plat_key, config={})

    step = _next_wizard_step(plat_key, {})
    if step:
        await _send_wizard_step(cb, state, plat_key, {}, step)
    else:
        await _show_confirm(cb, state)
    await cb.answer()


@router.callback_query(PartnerSt.config_step, F.data.startswith("fld_"))
async def cb_wizard_step(cb: CallbackQuery, state: FSMContext):
    # data format: fld_FIELDKEY__VALUE  (double underscore separates key from value)
    raw      = cb.data[4:]               # strip "fld_"
    sep      = raw.index("__")
    field    = raw[:sep]
    value    = raw[sep+2:]

    data     = await state.get_data()
    config   = data.get("config", {})
    plat_key = data["platform_key"]
    config[field] = value
    await state.update_data(config=config)

    next_step = _next_wizard_step(plat_key, config)
    if next_step:
        await _send_wizard_step(cb, state, plat_key, config, next_step)
    else:
        await _show_confirm(cb, state)
    await cb.answer()


async def _show_confirm(cb: CallbackQuery, state: FSMContext):
    data     = await state.get_data()
    config   = data.get("config", {})
    plat_key = data["platform_key"]
    mother   = storage.get_mother_sheet(data["mother_id"])
    plat     = PLATFORMS[plat_key]

    lines = "\n".join(f"  `{k}` → `{v}`" for k, v in config.items())
    await cb.message.edit_text(
        f"📋 *Confirm Sheet Creation*\n\n"
        f"Platform: {plat['name']}\n"
        f"Source: {mother['name']}\n"
        f"Library: `{plat['library_symbol']}`\n\n"
        f"Config:\n{lines}\n\n"
        f"Create?",
        parse_mode="Markdown",
        reply_markup=kb_confirm_create(),
    )
    await state.set_state(PartnerSt.confirm)


@router.callback_query(PartnerSt.confirm, F.data == "do_create")
async def cb_do_create(cb: CallbackQuery, state: FSMContext):
    data   = await state.get_data()
    p      = storage.get_partner(cb.from_user.id)
    mother = storage.get_mother_sheet(data["mother_id"])
    plat   = PLATFORMS[data["platform_key"]]

    await cb.message.edit_text("⏳ Creating your spreadsheet… (~30–60 sec)")
    await cb.answer()

    try:
        child = await asyncio.to_thread(
            gapi.create_child_sheet,
            partner_name=p["name"],
            platform_key=data["platform_key"],
            mother=mother,
        )
        storage.add_child_sheet(cb.from_user.id, child)
        await cb.message.edit_text(
            f"✅ *Sheet ready!*\n\n"
            f"🔗 [Open Spreadsheet]({child['spreadsheet_url']})\n\n"
            f"Platform: {plat['name']}\n"
            f"Library: `{plat['library_symbol']}`\n\n"
            f"_Next:_\n"
            f"1. Open the sheet\n"
            f"2. Paste raw data into *Raw Data* tab\n"
            f"3. Run 📊 ANALYSIS → Quality Tracking",
            parse_mode="Markdown",
            reply_markup=kb_partner_home(),
        )
    except Exception as exc:
        log.exception("create_child_sheet failed")
        await cb.message.edit_text(
            f"❌ Failed to create sheet.\n\n`{str(exc)[:300]}`\n\nContact admin.",
            parse_mode="Markdown",
            reply_markup=kb_partner_home(),
        )
    await state.clear()


@router.callback_query(F.data == "p_mysheets")
async def cb_p_mysheets(cb: CallbackQuery):
    p = storage.get_partner(cb.from_user.id)
    if not p: return await cb.answer("No access", show_alert=True)
    kids = p.get("child_sheets", [])
    if not kids:
        await cb.message.edit_text("You haven't created any sheets yet.",
                                   reply_markup=kb_partner_home())
    else:
        await cb.message.edit_text(
            f"📋 *Your Sheets* ({len(kids)} total)",
            parse_mode="Markdown",
            reply_markup=kb_partner_sheets(kids),
        )
    await cb.answer()


@router.callback_query(F.data.startswith("p_child_"))
async def cb_view_child(cb: CallbackQuery):
    sid = cb.data.replace("p_child_", "")
    p   = storage.get_partner(cb.from_user.id)
    c   = next((x for x in p.get("child_sheets", []) if x["spreadsheet_id"] == sid), None)
    if not c: return await cb.answer("Not found", show_alert=True)
    plat = PLATFORMS.get(c.get("platform", ""), {})
    await cb.message.edit_text(
        f"📊 *{plat.get('name','?')}*\n"
        f"Created: {c.get('created_at','')[:10]}\n\n"
        f"🔗 [Open Spreadsheet]({c['spreadsheet_url']})",
        parse_mode="Markdown",
        reply_markup=_ik([_btn("◀️ Back", "p_mysheets")]),
    )
    await cb.answer()


# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

async def main():
    global storage, gapi

    assert BOT_TOKEN, "BOT_TOKEN env var is not set"

    storage = Storage(DATA_FILE)
    gapi    = GoogleAPI(SERVICE_ACCOUNT_FILE)

    if FIRST_ADMIN_ID:
        storage.add_admin(FIRST_ADMIN_ID)
        log.info("First admin registered: %s", FIRST_ADMIN_ID)

    bot = Bot(token=BOT_TOKEN)
    dp  = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    log.info("Bot started")
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
