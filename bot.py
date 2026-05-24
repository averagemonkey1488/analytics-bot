#!/usr/bin/env python3
"""TD Analytics Toolkit Bot v3 — full feature set"""

import asyncio, json, logging, os
from datetime import datetime
from pathlib import Path
from typing import Optional

# ── write credential files from env vars ────────────────────────
for _env, _file in [("SERVICE_ACCOUNT_JSON","service_account.json"),("GOOGLE_TOKEN_JSON","token.json")]:
    _raw = os.getenv(_env,"").strip()
    if _raw:
        try:
            if _raw.startswith('"'): _raw=_raw[1:-1]
            _raw=_raw.replace('\\"','"')
            with open(_file,"w") as _f: json.dump(json.loads(_raw),_f,indent=2)
            print(f"{_file} written OK")
        except Exception as _e: print(f"WARNING {_file}: {_e}")
# ────────────────────────────────────────────────────────────────

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from google.oauth2.credentials import Credentials as OAuthCreds
from google.oauth2.service_account import Credentials as SACreds
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")
log = logging.getLogger(__name__)

BOT_TOKEN       = os.getenv("BOT_TOKEN","")
SA_FILE         = os.getenv("SERVICE_ACCOUNT_FILE","service_account.json")
TOKEN_FILE      = "token.json"
DATA_FILE       = os.getenv("DATA_FILE","data.json")
FIRST_ADMIN_ID  = int(os.getenv("FIRST_ADMIN_ID","0"))

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
        "name": "🎯 Cellexpert", "library_symbol": "ChinCore",
        "raw_sheet": "D",
        "raw_headers": ["User ID","Registration Date","Brand","afp","Country",
                        "Deposits","Deposit Count","Commission","Qualification Date",
                        "Tracking Code","Net Deposits"],
        "fields": {
            "webname":        {"label":"Webname field",  "default":"afp2","options":["afp1","afp2","afp3","afp4","afp6","afp10"]},
            "creo":           {"label":"Creo field",     "default":"afp6","options":["afp1","afp2","afp3","afp4","afp6","afp10"]},
            "clickid":        {"label":"Click ID field", "default":"afp1","options":["afp1","afp2","afp3","afp4","afp6","afp10"]},
            "target_oas":     {"label":"Target OAS",     "default":"55%"},
            "hr_top_percent": {"label":"HR Top %",       "default":"2%"},
        },
        "public_api": {
            "quality":"processFullReportBoth_Public","oas":"buildOASByWebBoth_Public",
            "export":"exportWebnameReports_Public","root_index":"openRootIndex_Public",
            "ex_config":"createExportConfig_Public","debug_map":"debugExportMapping_Public",
            "stop":"stopExport_Public","reset":"hardResetExportCache_Public",
            "chunk":"EX_exportChunk_Public","ping":"ChinCore_ping_Public",
        },
    },
    "referon": {
        "name": "📊 ReferOn", "library_symbol": "TDCore",
        "raw_sheet": "Raw Data",
        "raw_headers": ["Program Name","Media Item ID","Media Item Name","Brand Name","Brand ID",
                        "Geo","Reg. Count","FTD Count","FTD Amount","Deposits","Count of deposits",
                        "CPA","pubid","subid","var1","var2","var3","var4","var5","clickid"],
        "fields": {
            "webname":     {"label":"Webname field",  "default":"pubid",  "options":["pubid","subid","var1","var2","var3","var4","var5","clickid"]},
            "creo":        {"label":"Creo field",     "default":"var3",   "options":["var1","var2","var3","var4","var5","pubid","subid"]},
            "clickid":     {"label":"Click ID field", "default":"clickid","options":["clickid","click_id","var1","var2","var3","var4","var5"]},
            "target_oas":  {"label":"Target OAS",     "default":"55%"},
            "min_ftd_gate":{"label":"Min FTD Gate",   "default":"5"},
        },
        "public_api": {
            "quality":"processAllPrograms_Public","oas":"buildOASByWeb_Public",
            "export":"exportFeedsByRealWebname_Public","root_index":"openRootIndex_Public",
            "ex_config":"openExportConfig_Public","debug_map":"debugExportMapping_Public",
            "stop":"stopExportAndReset_Public","reset":"resetCache_Public",
            "chunk":"EX_exportChunk_Public","ping":"CPCore_ping_Public",
        },
    },
    "affilka_fb": {
        "name": "📱 Affilka FB", "library_symbol": "FBCore",
        "raw_sheet": "Raw Data",
        "raw_headers": ["Brand ID","Brand Name","Strategy","Campaign ID","Campaign name",
                        "Promo ID","Promo code","Promo name","Tag: afp2","Tag: afp3","Tag: afp4",
                        "Tag: afp1","Tag: afp10","First deposit date","Visits","Registrations",
                        "Depositors","Currency","FTD count","FTD sum","Deposits count","Deposits sum",
                        "Cashouts count","Cashouts sum","Partner income"],
        "fields": {
            "webname":        {"label":"Webname field",  "default":"afp1","options":["afp1","afp2","afp3","afp4","afp10","promo_code","promo_name"]},
            "creo":           {"label":"Creo field",     "default":"afp1","options":["afp1","afp2","afp3","afp4","afp10","promo_code","promo_name"]},
            "clickid":        {"label":"Click ID field", "default":"afp3","options":["afp1","afp2","afp3","afp4","afp10"]},
            "target_oas":     {"label":"Target OAS",     "default":"55%"},
            "hr_top_percent": {"label":"HR Top %",       "default":"2%"},
            "min_ftd_gate":   {"label":"Min FTD Gate",   "default":"5"},
        },
        "public_api": {
            "quality":"processAllPrograms_Public","oas":"buildOASByWeb_Public",
            "export":"exportFeedsByRealWebname_Public","root_index":"openRootIndex_Public",
            "ex_config":"openExportConfig_Public","debug_map":"debugExportMapping_Public",
            "normalize":"normalizeRawData_Public","debug_raw":"debugRawValues_Public",
            "stop":"stopExportAndReset_Public","reset":"resetCache_Public",
            "chunk":"EX_exportChunk_Public","ping":"CPCore_ping_Public",
        },
    },
    "affilka": {
        "name": "🔗 Affilka Standard", "library_symbol": "TDCoreV5",
        "raw_sheet": "Raw Data",
        "raw_headers": ["Program Name","Media Item ID","Media Item Name","Brand Name","Brand ID",
                        "Geo","Reg. Count","FTD Count","FTD Amount","Deposits","Count of deposits",
                        "CPA","pubid","subid","var1","var2","var3","var4","var5"],
        "fields": {
            "webname":     {"label":"Webname field",  "default":"pubid",  "options":["pubid","subid","var1","var2","var3","var4","var5"]},
            "creo":        {"label":"Creo field",     "default":"var3",   "options":["var1","var2","var3","var4","var5","pubid"]},
            "clickid":     {"label":"Click ID field", "default":"clickid","options":["clickid","var1","var2","var3","var4","var5"]},
            "target_oas":  {"label":"Target OAS",     "default":"55%"},
            "min_ftd_gate":{"label":"Min FTD Gate",   "default":"5"},
        },
        "public_api": {
            "quality":"processAllPrograms_Public","oas":"buildOASByWeb_Public",
            "export":"exportFeedsByRealWebname_Public","root_index":"openRootIndex_Public",
            "ex_config":"openExportConfig_Public","debug_map":"debugExportMapping_Public",
            "stop":"stopExportAndReset_Public","reset":"resetCache_Public",
            "chunk":"EX_exportChunk_Public","ping":"CPCore_ping_Public",
        },
    },
}

WIZARD_STEPS = ["webname","creo","clickid","target_oas","min_ftd_gate","hr_top_percent"]

# ═══════════════════════════════════════════════════════════════
# GAS GENERATOR
# ═══════════════════════════════════════════════════════════════
def build_loader_script(platform_key: str) -> str:
    p=PLATFORMS[platform_key]; sym=p["library_symbol"]; api=p["public_api"]
    a_items=["    .addItem('📈 Quality Tracking','_runQuality')","    .addItem('🎯 OAS Tracking','_runOAS')","    .addSeparator()","    .addItem('📦 Webname Export','_runExport')","    .addItem('🗂 Open Root Index','_runRootIndex')"]
    if platform_key=="affilka_fb": a_items+=["    .addSeparator()","    .addItem('🔧 Normalize Raw Data','_runNormalize')"]
    t_items=["    .addItem('⚙️ Export Config','_runExConfig')","    .addItem('🔍 Debug Export Mapping','_runDebugMap')"]
    if platform_key=="affilka_fb": t_items.append("    .addItem('🔢 Debug Raw Values','_runDebugRaw')")
    t_items+=["    .addSeparator()","    .addItem('🛑 Stop / Reset Export','_runStop')","    .addSeparator()","    .addItem('💥 HARD Reset Cache','_runReset')","    .addSeparator()","    .addItem('✅ Test Connection','_runPing')"]
    def fn(n,c): return f"function {n}() {{ {sym}.{c}(); }}"
    fns=[fn("_runQuality",api["quality"]),fn("_runOAS",api["oas"]),fn("_runExport",api["export"]),fn("_runRootIndex",api["root_index"]),fn("_runExConfig",api["ex_config"]),fn("_runDebugMap",api["debug_map"]),fn("_runStop",api["stop"]),fn("_runReset",api["reset"]),f"function EX_exportChunk_Loader() {{ {sym}.{api['chunk']}(); }}"]
    if platform_key=="affilka_fb": fns+=[fn("_runNormalize",api["normalize"]),fn("_runDebugRaw",api["debug_raw"])]
    fns.append(f"function _runPing() {{\n  var r={sym}.{api['ping']}();\n  SpreadsheetApp.getUi().alert(r);\n}}")
    nl="\n"
    return (f"// Auto-generated — {p['name']} — {datetime.utcnow():%Y-%m-%d %H:%M} UTC\n// Library: {sym}\n\n"
            f"function onOpen() {{\n  var ui=SpreadsheetApp.getUi();\n  ui.createMenu('📊 ANALYSIS')\n{nl.join(a_items)}\n    .addToUi();\n"
            f"  ui.createMenu('🛠 TECH PANEL')\n{nl.join(t_items)}\n    .addToUi();\n}}\n\n"+"\n".join(fns))

def build_manifest(library_symbol: str, script_id: str) -> str:
    return json.dumps({"timeZone":"Europe/London","dependencies":{"libraries":[{"userSymbol":library_symbol,"libraryId":script_id,"version":"1","developmentMode":True}]},"exceptionLogging":"STACKDRIVER","runtimeVersion":"V8"},indent=2)

# ═══════════════════════════════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════════════════════════════
class Storage:
    def __init__(self,path):
        self._path=path; self._d=self._load()

    def _load(self):
        if Path(self._path).exists():
            with open(self._path,encoding="utf-8") as f: return json.load(f)
        return {"superadmin_id":0,"admins":[],"mother_sheets":{},"partners":{},"platform_scripts":{},"platform_faqs":{},"partner_scripts":{},"partner_faqs":{}}

    def _save(self):
        with open(self._path,"w",encoding="utf-8") as f: json.dump(self._d,f,indent=2,ensure_ascii=False)

    def _ensure_keys(self):
        for k in ["superadmin_id","admins","mother_sheets","partners","platform_scripts","platform_faqs","partner_scripts","partner_faqs"]:
            if k not in self._d: self._d[k]=0 if k=="superadmin_id" else {} if k!="admins" else []

    # roles
    def is_superadmin(self,uid): return uid==self._d.get("superadmin_id",0)
    def is_admin(self,uid): return self.is_superadmin(uid) or uid in self._d.get("admins",[])
    def set_superadmin(self,uid): self._ensure_keys(); self._d["superadmin_id"]=uid; self._save()
    def add_admin(self,uid):
        self._ensure_keys()
        if uid and uid not in self._d["admins"]: self._d["admins"].append(uid); self._save()
    def remove_admin(self,uid):
        if uid in self._d.get("admins",[]): self._d["admins"].remove(uid); self._save()
    def all_admins(self): return self._d.get("admins",[])

    # mother sheets
    def add_mother_sheet(self,sheet_id,name,script_id,platform):
        self._ensure_keys()
        e={"id":sheet_id,"name":name,"script_id":script_id,"platform":platform,"library_symbol":PLATFORMS[platform]["library_symbol"],"created_at":datetime.utcnow().isoformat()}
        self._d["mother_sheets"][sheet_id]=e; self._save(); return e
    def get_mother_sheet(self,sid): return self._d.get("mother_sheets",{}).get(sid)
    def all_mother_sheets(self): return self._d.get("mother_sheets",{})
    def remove_mother_sheet(self,sid): self._d.get("mother_sheets",{}).pop(sid,None); self._save()
    def update_mother_sheet(self,sid,patch):
        if sid in self._d.get("mother_sheets",{}): self._d["mother_sheets"][sid].update(patch); self._save()

    # partners
    def add_partner(self,uid,name,username=""):
        self._ensure_keys()
        e={"telegram_id":uid,"name":name,"username":username,"assigned_sheet_ids":[],"child_sheets":[],"active":True,"created_at":datetime.utcnow().isoformat()}
        self._d["partners"][str(uid)]=e; self._save(); return e
    def get_partner(self,uid): return self._d.get("partners",{}).get(str(uid))
    def all_partners(self): return self._d.get("partners",{})
    def update_partner(self,uid,patch):
        p=self.get_partner(uid)
        if p: p.update(patch); self._d["partners"][str(uid)]=p; self._save()
    def assign_sheet(self,uid,sid):
        p=self.get_partner(uid)
        if p and sid not in p.get("assigned_sheet_ids",[]): p.setdefault("assigned_sheet_ids",[]).append(sid); self._save()
    def unassign_sheet(self,uid,sid):
        p=self.get_partner(uid)
        if p and sid in p.get("assigned_sheet_ids",[]): p["assigned_sheet_ids"].remove(sid); self._save()
    def add_child_sheet(self,uid,child):
        p=self.get_partner(uid)
        if p: p.setdefault("child_sheets",[]).append(child); self._save()
    def partner_assigned_sheets(self,uid):
        p=self.get_partner(uid)
        if not p: return []
        return [self.get_mother_sheet(s) for s in p.get("assigned_sheet_ids",[]) if self.get_mother_sheet(s)]

    # scripts & faqs
    def set_platform_script(self,platform,code): self._ensure_keys(); self._d["platform_scripts"][platform]=code; self._save()
    def get_platform_script(self,platform): return self._d.get("platform_scripts",{}).get(platform)
    def set_partner_script(self,uid,platform,code): self._ensure_keys(); self._d["partner_scripts"].setdefault(str(uid),{})[platform]=code; self._save()
    def get_partner_script(self,uid,platform): return self._d.get("partner_scripts",{}).get(str(uid),{}).get(platform)
    def set_platform_faq(self,platform,content): self._ensure_keys(); self._d["platform_faqs"][platform]=content; self._save()
    def get_platform_faq(self,platform): return self._d.get("platform_faqs",{}).get(platform)

    # get all child sheets across all partners for a platform
    def all_child_sheets_for_platform(self,platform):
        result=[]
        for uid,p in self._d.get("partners",{}).items():
            for cs in p.get("child_sheets",[]):
                if cs.get("platform")==platform: result.append({"uid":int(uid),"partner":p["name"],"sheet":cs})
        return result

# ═══════════════════════════════════════════════════════════════
# CREDENTIALS
# ═══════════════════════════════════════════════════════════════
def load_creds():
    if Path(TOKEN_FILE).exists():
        try:
            data=json.loads(Path(TOKEN_FILE).read_text())
            c=OAuthCreds(token=data.get("token"),refresh_token=data.get("refresh_token"),token_uri=data.get("token_uri","https://oauth2.googleapis.com/token"),client_id=data.get("client_id"),client_secret=data.get("client_secret"),scopes=data.get("scopes",GOOGLE_SCOPES))
            if c.expired and c.refresh_token: c.refresh(Request())
            log.info("OAuth credentials loaded"); return c
        except Exception as e: log.warning("token.json failed: %s",e)
    if Path(SA_FILE).exists():
        log.info("Service account credentials loaded")
        return SACreds.from_service_account_file(SA_FILE,scopes=GOOGLE_SCOPES)
    raise RuntimeError("No Google credentials. Set GOOGLE_TOKEN_JSON env var.")

# ═══════════════════════════════════════════════════════════════
# GOOGLE API
# ═══════════════════════════════════════════════════════════════
class GoogleAPI:
    def __init__(self):
        c=load_creds()
        self._sheets=build("sheets","v4",credentials=c)
        self._drive =build("drive", "v3",credentials=c)
        self._script=build("script","v1",credentials=c)
        log.info("Google API ready")

    def create_spreadsheet(self,title):
        res=self._drive.files().create(body={"name":title,"mimeType":"application/vnd.google-apps.spreadsheet"},fields="id,webViewLink").execute()
        fid=res["id"]; url=res.get("webViewLink",f"https://docs.google.com/spreadsheets/d/{fid}/edit")
        log.info("Spreadsheet created: %s",fid)
        return {"id":fid,"url":url}

    def share_anyone_write(self,fid):
        self._drive.permissions().create(fileId=fid,body={"type":"anyone","role":"writer"},fields="id").execute()

    def init_spreadsheet(self,sid,platform_key,config,advertiser):
        """Rename default sheet, add Webname Map, pre-fill Config Parser & Export Config."""
        plat=PLATFORMS[platform_key]
        raw_name=plat["raw_sheet"]
        # Step 1: rename Sheet1 + add extra sheets
        reqs=[{"updateSheetProperties":{"properties":{"sheetId":0,"title":raw_name},"fields":"title"}},
              {"addSheet":{"properties":{"title":"Webname Map"}}},
              {"addSheet":{"properties":{"title":"Config Parser"}}},
              {"addSheet":{"properties":{"title":"Export Config"}}},]
        self._sheets.spreadsheets().batchUpdate(spreadsheetId=sid,body={"requests":reqs}).execute()

        # Step 2: write Raw Data headers
        self._sheets.spreadsheets().values().update(
            spreadsheetId=sid, range=f"'{raw_name}'!A1",
            valueInputOption="RAW",body={"values":[plat["raw_headers"]]}).execute()

        # Step 3: Webname Map headers
        self._sheets.spreadsheets().values().update(
            spreadsheetId=sid, range="'Webname Map'!A1",
            valueInputOption="RAW",body={"values":[["Webname (raw/fake)","Real Webname","Team"]]}).execute()

        # Step 4: Config Parser pre-fill
        cfg_rows=[["Parameter","Value","Допустимые значения","Описание"]]
        for field_key,field_def in plat["fields"].items():
            val=config.get(field_key,field_def.get("default",""))
            opts=" / ".join(field_def.get("options",[])) or field_def.get("default","")
            cfg_rows.append([field_key,val,opts,field_def["label"]])
        self._sheets.spreadsheets().values().update(
            spreadsheetId=sid, range="'Config Parser'!A1",
            valueInputOption="RAW",body={"values":cfg_rows}).execute()

        # Step 5: Export Config pre-fill
        partner_folder=f"[{advertiser}] ANALYSIS"
        sheet_name   =f"[{advertiser}] Analysis"
        ex_rows=[["Parameter","Value","Required","Comment"],
                 ["SHARED_ROOT_FOLDER_ID","","YES","ID корневой папки Google Drive"],
                 ["ROOT_EXPORTS_FOLDER","Root Exports","YES","Главная папка"],
                 ["PARTNER_FOLDER",partner_folder,"YES","Папка партнёра"],
                 ["EXPORT_SHEET_NAME",sheet_name,"YES","Префикс листов"],
                 ["CHUNK_SIZE","25","NO","Файлов за один запуск"],
                 ["— Режимы экспорта —","","",""],
                 ["EXPORT_SIMPLE","YES","YES","Grand Total → Brand+Geo → Web"],
                 ["EXPORT_ANALYSIS","NO","NO","Лист Analysis"],
                 ["EXPORT_ANALYSIS_MAIN","NO","NO","Лист Analysis_Main"],
                 ["EXPORT_CREO","NO","NO","Лист Creo Analysis"],
                 ["EXPORT_MEDIAITEM","NO","NO","Лист MediaItem Analysis"]]
        self._sheets.spreadsheets().values().update(
            spreadsheetId=sid, range="'Export Config'!A1",
            valueInputOption="RAW",body={"values":ex_rows}).execute()
        log.info("Spreadsheet initialized for %s",platform_key)

    def create_bound_script(self,sid,title):
        res=self._script.projects().create(body={"title":title,"parentId":sid}).execute()
        return res["scriptId"]

    def push_script_files(self,script_id,loader_js,manifest_json):
        self._script.projects().updateContent(scriptId=script_id,body={"files":[
            {"name":"appsscript","type":"JSON","source":manifest_json},
            {"name":"Loader","type":"SERVER_JS","source":loader_js},
        ]}).execute()

    def push_library_code(self,script_id,code):
        """Push new GAS library code to a mother sheet's script project."""
        self._script.projects().updateContent(scriptId=script_id,body={"files":[
            {"name":"appsscript","type":"JSON","source":json.dumps({"timeZone":"Europe/London","exceptionLogging":"STACKDRIVER","runtimeVersion":"V8"},indent=2)},
            {"name":"Code","type":"SERVER_JS","source":code},
        ]}).execute()

    def create_or_update_faq_sheet(self,spreadsheet_id,faq_content):
        """Create/update FAQ sheet in a spreadsheet with given content."""
        # Check if FAQ sheet exists
        meta=self._sheets.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        existing=[s["properties"]["title"] for s in meta.get("sheets",[])]
        if "FAQ" not in existing:
            self._sheets.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id,body={"requests":[{"addSheet":{"properties":{"title":"FAQ"}}}]}).execute()
        # Write content
        rows=[[line] for line in faq_content.split("\n")]
        self._sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,range="FAQ!A1",
            valueInputOption="RAW",body={"values":rows}).execute()

    def create_child_sheet(self,partner_name,platform_key,mother,config,advertiser):
        plat=PLATFORMS[platform_key]
        title=f"{advertiser} | {partner_name} | Quality Analysis — EXTERNAL"
        ss=self.create_spreadsheet(title)
        self.init_spreadsheet(ss["id"],platform_key,config,advertiser)
        loader  =build_loader_script(platform_key)
        manifest=build_manifest(plat["library_symbol"],mother["script_id"])
        script_id=self.create_bound_script(ss["id"],f"{title} Script")
        self.push_script_files(script_id,loader,manifest)
        self.share_anyone_write(ss["id"])
        return {"spreadsheet_id":ss["id"],"spreadsheet_url":ss["url"],"script_id":script_id,
                "platform":platform_key,"mother_sheet_id":mother["id"],"advertiser":advertiser,
                "created_at":datetime.utcnow().isoformat()}

# ═══════════════════════════════════════════════════════════════
# FSM STATES
# ═══════════════════════════════════════════════════════════════
class AdminSt(StatesGroup):
    add_partner_id=State(); add_partner_name=State()
    add_sheet_id=State(); add_sheet_name=State(); add_script_id=State(); add_platform=State()
    add_admin_id=State()
    update_script_platform=State(); update_script_code=State(); update_script_note=State()
    update_faq_platform=State(); update_faq_content=State()

class PartnerSt(StatesGroup):
    advertiser=State(); pick_mother=State(); config_step=State(); confirm=State()

# ═══════════════════════════════════════════════════════════════
# KEYBOARDS
# ═══════════════════════════════════════════════════════════════
def _ik(*rows): return InlineKeyboardMarkup(inline_keyboard=list(rows))
def _btn(t,d): return InlineKeyboardButton(text=t,callback_data=d)

def kb_admin_home():
    return _ik([_btn("👥 Partners","adm_partners"),_btn("📋 Mother Sheets","adm_sheets")],
               [_btn("🔗 Assign Sheets","adm_assign_sel"),_btn("📊 All Sheets","adm_all_sheets")],
               [_btn("🔄 Update Script","adm_upd_script"),_btn("📄 Update FAQ","adm_upd_faq")],
               [_btn("👑 Manage Admins","adm_manage_admins")])

def kb_admin_partners(partners):
    rows=[[_btn(f"{'✅' if p.get('active') else '❌'} {p['name']}",f"adm_p_{uid}")] for uid,p in list(partners.items())[:15]]
    rows.append([_btn("➕ Add","adm_add_partner"),_btn("◀️ Back","adm_home")]); return _ik(*rows)

def kb_admin_sheets(sheets):
    rows=[[_btn(f"{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}",f"adm_s_{sid}")] for sid,s in list(sheets.items())[:15]]
    rows.append([_btn("➕ Add","adm_add_sheet"),_btn("◀️ Back","adm_home")]); return _ik(*rows)

def kb_platforms(prefix="plat"):
    rows=[[_btn(p["name"],f"{prefix}_{k}")] for k,p in PLATFORMS.items()]
    rows.append([_btn("❌ Cancel","cancel")]); return _ik(*rows)

def kb_field_options(field_key,options):
    rows,row=[],[]
    for opt in options:
        row.append(_btn(opt,f"fld_{field_key}__{opt}"))
        if len(row)==3: rows.append(row); row=[]
    if row: rows.append(row)
    rows.append([_btn("⏭ Skip (use default)",f"fld_{field_key}__SKIP")])
    return _ik(*rows)

def kb_oas():    return _ik([_btn("50%","fld_target_oas__50%"),_btn("55% ✦","fld_target_oas__55%"),_btn("60%","fld_target_oas__60%"),_btn("65%","fld_target_oas__65%")],[_btn("⏭ Skip","fld_target_oas__SKIP")])
def kb_ftd():    return _ik([_btn("3","fld_min_ftd_gate__3"),_btn("5 ✦","fld_min_ftd_gate__5"),_btn("10","fld_min_ftd_gate__10")],[_btn("⏭ Skip","fld_min_ftd_gate__SKIP")])
def kb_hr():     return _ik([_btn("1%","fld_hr_top_percent__1%"),_btn("2% ✦","fld_hr_top_percent__2%"),_btn("5%","fld_hr_top_percent__5%")],[_btn("⏭ Skip","fld_hr_top_percent__SKIP")])
def kb_confirm():return _ik([_btn("✅ Create","do_create"),_btn("❌ Cancel","cancel")])
def kb_partner_home():return _ik([_btn("➕ Create New Sheet","p_create")],[_btn("📋 My Sheets","p_mysheets")])

def kb_select_mother(sheets):
    rows=[[_btn(f"{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}",f"p_mother_{s['id']}")] for s in sheets]
    rows.append([_btn("❌ Cancel","cancel")]); return _ik(*rows)

def kb_partner_sheets(kids):
    rows=[[_btn(f"{k.get('advertiser','?')} | {PLATFORMS.get(k.get('platform',''),{}).get('name','?')} — {k.get('created_at','')[:10]}",f"p_child_{k['spreadsheet_id']}")] for k in kids[-15:]]
    rows.append([_btn("◀️ Back","p_home")]); return _ik(*rows)

def kb_assign_sheets(partner,sheets):
    assigned=partner.get("assigned_sheet_ids",[])
    rows=[]
    for sid,s in sheets.items():
        mark="✅ " if sid in assigned else ""
        act=f"unassign_{partner['telegram_id']}_{sid}" if sid in assigned else f"assign_{partner['telegram_id']}_{sid}"
        rows.append([_btn(f"{mark}{PLATFORMS.get(s['platform'],{}).get('name','?')} — {s['name']}",act)])
    rows.append([_btn("◀️ Back",f"adm_p_{partner['telegram_id']}")])
    return _ik(*rows)

def kb_quick_add_partner(uid,username):
    return _ik([_btn("➕ Add as Partner",f"quick_add_{uid}")],[_btn("❌ Ignore",f"quick_ignore_{uid}")])

# ═══════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════
def _next_step(platform_key,config):
    for step in WIZARD_STEPS:
        if step in PLATFORMS[platform_key]["fields"] and step not in config:
            return step
    return None

async def _send_step(target,state,platform_key,config,step):
    field=PLATFORMS[platform_key]["fields"][step]
    text=f"⚙️ *{field['label']}*\nDefault: `{field.get('default','')}`"
    kb_map={"target_oas":kb_oas,"min_ftd_gate":kb_ftd,"hr_top_percent":kb_hr}
    kb=kb_map.get(step,lambda:kb_field_options(step,field.get("options",[])))
    if isinstance(target,Message): await target.answer(text,parse_mode="Markdown",reply_markup=kb())
    else: await target.message.edit_text(text,parse_mode="Markdown",reply_markup=kb())
    await state.set_state(PartnerSt.config_step)

def resolve_skip(field_key,platform_key):
    """Return default value for a skipped field."""
    return PLATFORMS[platform_key]["fields"][field_key].get("default","")

# ═══════════════════════════════════════════════════════════════
# ROUTER
# ═══════════════════════════════════════════════════════════════
router=Router()
storage: Storage=None
gapi:    GoogleAPI=None
bot_instance: Bot=None

# ── common ────────────────────────────────────────────────────
@router.message(CommandStart())
async def cmd_start(msg: Message):
    uid=msg.from_user.id
    if storage.is_admin(uid):
        await msg.answer("👑 Admin Panel",reply_markup=kb_admin_home())
    elif p:=storage.get_partner(uid):
        if not p.get("active"): return await msg.answer("❌ Inactive. Contact admin.")
        await msg.answer(f"👋 Welcome, {p['name']}!",reply_markup=kb_partner_home())
    else:
        await msg.answer("👋 Welcome! Your request has been sent to the admin.")
        # Notify all admins
        uname=f"@{msg.from_user.username}" if msg.from_user.username else "no username"
        name=msg.from_user.full_name
        notify=f"🔔 *New user wants access*\n\nName: {name}\nUsername: {uname}\nID: `{uid}`\n\nAdd as partner?"
        admins=[storage._d.get("superadmin_id",0)]+storage.all_admins()
        for aid in set(a for a in admins if a):
            try: await bot_instance.send_message(aid,notify,parse_mode="Markdown",reply_markup=kb_quick_add_partner(uid,uname))
            except: pass

@router.message(Command("admin"))
async def cmd_admin(msg: Message):
    if storage.is_admin(msg.from_user.id): await msg.answer("👑 Admin Panel",reply_markup=kb_admin_home())

@router.message(Command("sheets"))
async def cmd_sheets(msg: Message):
    uid=msg.from_user.id
    if storage.is_admin(uid):
        # Admin: show all partners + their sheets
        lines=["📊 *All Sheets*\n"]
        for p_uid,p in storage.all_partners().items():
            kids=p.get("child_sheets",[])
            if not kids: continue
            lines.append(f"👤 *{p['name']}*")
            for k in kids:
                plat=PLATFORMS.get(k.get("platform",""),{}).get("name","?")
                adv=k.get("advertiser","?")
                url=k.get("spreadsheet_url","")
                lines.append(f"  • {adv} | {plat} — [открыть]({url})")
            lines.append("")
        if len(lines)==1: lines.append("No sheets yet.")
        await msg.answer("\n".join(lines),parse_mode="Markdown",disable_web_page_preview=True)
    elif p:=storage.get_partner(uid):
        kids=p.get("child_sheets",[])
        if not kids: return await msg.answer("No sheets yet.")
        lines=[f"📋 *Your Sheets* ({len(kids)})\n"]
        for k in kids:
            plat=PLATFORMS.get(k.get("platform",""),{}).get("name","?")
            adv=k.get("advertiser","?")
            url=k.get("spreadsheet_url","")
            lines.append(f"• {adv} | {plat} — [открыть]({url})")
        await msg.answer("\n".join(lines),parse_mode="Markdown",disable_web_page_preview=True)

@router.message(Command("testapi"))
async def cmd_testapi(msg: Message):
    if not storage.is_admin(msg.from_user.id): return
    tok=Path(TOKEN_FILE).exists(); sa=Path(SA_FILE).exists()
    await msg.answer(f"1️⃣ Creds: `{'OAuth' if tok else 'SA' if sa else 'NONE'}`",parse_mode="Markdown")
    try:
        c=load_creds(); await msg.answer(f"2️⃣ Auth: ✅",parse_mode="Markdown")
    except Exception as e: return await msg.answer(f"2️⃣ Auth: ❌\n`{e}`",parse_mode="Markdown")
    try:
        dr=build("drive","v3",credentials=c)
        res=dr.files().create(body={"name":"_API_TEST_","mimeType":"application/vnd.google-apps.spreadsheet"},fields="id").execute()
        cid=res["id"]; await msg.answer(f"3️⃣ Drive: ✅\n`{cid}`",parse_mode="Markdown")
        sc=build("script","v1",credentials=c)
        sp=sc.projects().create(body={"title":"_TEST_","parentId":cid}).execute()
        await msg.answer(f"4️⃣ Script: ✅\n`{sp['scriptId']}`",parse_mode="Markdown")
        await msg.answer(f"🧹 Delete: https://docs.google.com/spreadsheets/d/{cid}/edit")
    except Exception as e: await msg.answer(f"❌\n`{e}`",parse_mode="Markdown")

@router.callback_query(F.data=="cancel")
async def cb_cancel(cb: CallbackQuery,state: FSMContext):
    await state.clear(); uid=cb.from_user.id
    if storage.is_admin(uid): await cb.message.edit_text("Cancelled.",reply_markup=kb_admin_home())
    elif storage.get_partner(uid): await cb.message.edit_text("Cancelled.",reply_markup=kb_partner_home())
    else: await cb.message.edit_text("Cancelled.")
    await cb.answer()

# ── quick add from notification ────────────────────────────────
@router.callback_query(F.data.startswith("quick_add_"))
async def cb_quick_add(cb: CallbackQuery,state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    uid=int(cb.data.replace("quick_add_",""))
    await state.update_data(new_uid=uid)
    await cb.message.edit_text(f"Enter a *name* for partner `{uid}`:",parse_mode="Markdown")
    await state.set_state(AdminSt.add_partner_name); await cb.answer()

@router.callback_query(F.data.startswith("quick_ignore_"))
async def cb_quick_ignore(cb: CallbackQuery):
    await cb.message.edit_text("Ignored."); await cb.answer()

# ── admin home ────────────────────────────────────────────────
@router.callback_query(F.data=="adm_home")
async def cb_adm_home(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    await cb.message.edit_text("👑 Admin Panel",reply_markup=kb_admin_home()); await cb.answer()

# ── all sheets ────────────────────────────────────────────────
@router.callback_query(F.data=="adm_all_sheets")
async def cb_all_sheets(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    lines=["📊 *All Sheets*\n"]
    # Mother sheets
    lines.append("*📋 Mother Sheets:*")
    for sid,s in storage.all_mother_sheets().items():
        plat=PLATFORMS.get(s["platform"],{}).get("name","?")
        lines.append(f"  • {s['name']} ({plat})\n    `{sid}`")
    lines.append("")
    # Child sheets by partner
    lines.append("*👤 Child Sheets:*")
    for p_uid,p in storage.all_partners().items():
        kids=p.get("child_sheets",[])
        if not kids: continue
        lines.append(f"\n*{p['name']}:*")
        for k in kids:
            plat=PLATFORMS.get(k.get("platform",""),{}).get("name","?")
            adv=k.get("advertiser","?")
            url=k.get("spreadsheet_url","")
            lines.append(f"  • {adv} | {plat}\n    [открыть]({url})")
    await cb.message.edit_text("\n".join(lines) if len(lines)>2 else "No sheets yet.",
                               parse_mode="Markdown",disable_web_page_preview=True,
                               reply_markup=_ik([_btn("◀️ Back","adm_home")])); await cb.answer()

# ── partners ──────────────────────────────────────────────────
@router.callback_query(F.data=="adm_partners")
async def cb_adm_partners(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    pp=storage.all_partners()
    await cb.message.edit_text(f"👥 Partners ({len(pp)})",reply_markup=kb_admin_partners(pp)); await cb.answer()

@router.callback_query(F.data=="adm_add_partner")
async def cb_adm_add_partner(cb: CallbackQuery,state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    await cb.message.edit_text("Enter partner's *Telegram ID*.\nForward their message to @userinfobot.",parse_mode="Markdown")
    await state.set_state(AdminSt.add_partner_id); await cb.answer()

@router.message(AdminSt.add_partner_id)
async def msg_partner_id(msg: Message,state: FSMContext):
    try: uid=int(msg.text.strip())
    except ValueError: return await msg.answer("❌ Must be a number:")
    await state.update_data(new_uid=uid)
    await msg.answer(f"ID: `{uid}`\n\nEnter a *name*:",parse_mode="Markdown")
    await state.set_state(AdminSt.add_partner_name)

@router.message(AdminSt.add_partner_name)
async def msg_partner_name(msg: Message,state: FSMContext):
    data=await state.get_data(); name=msg.text.strip()
    storage.add_partner(data["new_uid"],name)
    await state.clear()
    # Notify new partner
    try: await bot_instance.send_message(data["new_uid"],f"✅ You have been added as a partner: *{name}*\n\nUse /start to begin.",parse_mode="Markdown")
    except: pass
    await msg.answer(f"✅ Partner *{name}* added!",parse_mode="Markdown",reply_markup=kb_admin_home())

@router.callback_query(F.data.startswith("adm_p_"))
async def cb_view_partner(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    uid=int(cb.data.replace("adm_p_","")); p=storage.get_partner(uid)
    if not p: return await cb.answer("Not found",show_alert=True)
    assigned=storage.partner_assigned_sheets(uid)
    kids=p.get("child_sheets",[])
    sheets_text="\n".join(f"  • {s['name']}" for s in assigned) or "  (none)"
    kids_text="\n".join(f"  • {k.get('advertiser','?')} | {PLATFORMS.get(k.get('platform',''),{}).get('name','?')}" for k in kids[-5:]) or "  (none)"
    await cb.message.edit_text(
        f"👤 *{p['name']}*\nID: `{uid}`\nStatus: {'✅ Active' if p.get('active') else '❌ Inactive'}\n"
        f"Child sheets: {len(kids)}\n\nAssigned mothers:\n{sheets_text}\n\nRecent sheets:\n{kids_text}",
        parse_mode="Markdown",
        reply_markup=_ik([_btn("🔗 Assign/Remove Sheets",f"adm_assign_{uid}")],
                         [_btn("❌ Deactivate" if p.get("active") else "✅ Activate",f"adm_toggle_{uid}")],
                         [_btn("◀️ Back","adm_partners")])); await cb.answer()

@router.callback_query(F.data.startswith("adm_toggle_"))
async def cb_toggle(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    uid=int(cb.data.replace("adm_toggle_","")); p=storage.get_partner(uid)
    if p: storage.update_partner(uid,{"active":not p.get("active",True)}); await cb.answer("Updated ✅")
    await cb_view_partner(cb)

# ── mother sheets ─────────────────────────────────────────────
@router.callback_query(F.data=="adm_sheets")
async def cb_adm_sheets(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    ss=storage.all_mother_sheets()
    await cb.message.edit_text(f"📋 Mother Sheets ({len(ss)})",reply_markup=kb_admin_sheets(ss)); await cb.answer()

@router.callback_query(F.data=="adm_add_sheet")
async def cb_add_sheet(cb: CallbackQuery,state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    await cb.message.edit_text("Enter *Spreadsheet ID*\n_(URL: …/spreadsheets/d/`[ID]`/edit)_",parse_mode="Markdown")
    await state.set_state(AdminSt.add_sheet_id); await cb.answer()

@router.message(AdminSt.add_sheet_id)
async def msg_sheet_id(msg: Message,state: FSMContext):
    await state.update_data(sheet_id=msg.text.strip())
    await msg.answer("Enter a *display name*:",parse_mode="Markdown")
    await state.set_state(AdminSt.add_sheet_name)

@router.message(AdminSt.add_sheet_name)
async def msg_sheet_name(msg: Message,state: FSMContext):
    await state.update_data(sheet_name=msg.text.strip())
    await msg.answer("Enter *Apps Script Project ID* (library).\nscript.google.com → ⚙️ Project Settings → Script ID",parse_mode="Markdown")
    await state.set_state(AdminSt.add_script_id)

@router.message(AdminSt.add_script_id)
async def msg_script_id(msg: Message,state: FSMContext):
    await state.update_data(script_id=msg.text.strip())
    await msg.answer("Select *platform*:",parse_mode="Markdown",reply_markup=kb_platforms())
    await state.set_state(AdminSt.add_platform)

@router.callback_query(AdminSt.add_platform,F.data.startswith("plat_"))
async def cb_sheet_platform(cb: CallbackQuery,state: FSMContext):
    plat_key=cb.data.replace("plat_",""); data=await state.get_data()
    sheet=storage.add_mother_sheet(data["sheet_id"],data["sheet_name"],data["script_id"],plat_key)
    await state.clear()
    await cb.message.edit_text(f"✅ *{sheet['name']}* added!\nPlatform: {PLATFORMS[plat_key]['name']}\nLibrary: `{sheet['library_symbol']}`",
                               parse_mode="Markdown",reply_markup=kb_admin_home()); await cb.answer()

@router.callback_query(F.data.startswith("adm_s_"))
async def cb_view_sheet(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    sid=cb.data.replace("adm_s_",""); s=storage.get_mother_sheet(sid)
    if not s: return await cb.answer("Not found",show_alert=True)
    await cb.message.edit_text(
        f"📋 *{s['name']}*\nPlatform: {PLATFORMS.get(s['platform'],{}).get('name','?')}\n"
        f"Library: `{s['library_symbol']}`\nScript ID: `{s['script_id']}`\nSheet ID: `{s['id']}`",
        parse_mode="Markdown",
        reply_markup=_ik([_btn("🗑 Remove",f"adm_rmsheet_{sid}"),_btn("◀️ Back","adm_sheets")])); await cb.answer()

@router.callback_query(F.data.startswith("adm_rmsheet_"))
async def cb_rm_sheet(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    storage.remove_mother_sheet(cb.data.replace("adm_rmsheet_","")); await cb.answer("Removed"); await cb_adm_sheets(cb)

# ── assign ────────────────────────────────────────────────────
@router.callback_query(F.data=="adm_assign_sel")
async def cb_assign_sel(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    pp=storage.all_partners()
    if not pp: return await cb.answer("No partners yet",show_alert=True)
    rows=[[_btn(p["name"],f"adm_assign_{uid}")] for uid,p in pp.items()]
    rows.append([_btn("◀️ Back","adm_home")])
    await cb.message.edit_text("Select partner:",reply_markup=_ik(*rows)); await cb.answer()

@router.callback_query(F.data.startswith("adm_assign_"))
async def cb_assign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    uid=int(cb.data.replace("adm_assign_","")); p=storage.get_partner(uid); ss=storage.all_mother_sheets()
    if not p or not ss: return await cb.answer("Nothing to assign",show_alert=True)
    await cb.message.edit_text(f"Toggle sheets for *{p['name']}*:",parse_mode="Markdown",reply_markup=kb_assign_sheets(p,ss)); await cb.answer()

@router.callback_query(F.data.startswith("assign_"))
async def cb_do_assign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    _,uid_s,sid=cb.data.split("_",2); storage.assign_sheet(int(uid_s),sid); await cb.answer("Assigned ✅")
    cb.data=f"adm_assign_{uid_s}"; await cb_assign(cb)

@router.callback_query(F.data.startswith("unassign_"))
async def cb_do_unassign(cb: CallbackQuery):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    _,uid_s,sid=cb.data.split("_",2); storage.unassign_sheet(int(uid_s),sid); await cb.answer("Unassigned")
    cb.data=f"adm_assign_{uid_s}"; await cb_assign(cb)

# ── script update ─────────────────────────────────────────────
@router.callback_query(F.data=="adm_upd_script")
async def cb_upd_script(cb: CallbackQuery,state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    await cb.message.edit_text("Select *platform* to update script:",parse_mode="Markdown",reply_markup=kb_platforms("upd_script"))
    await state.set_state(AdminSt.update_script_platform); await cb.answer()

@router.callback_query(AdminSt.update_script_platform,F.data.startswith("upd_script_"))
async def cb_upd_script_platform(cb: CallbackQuery,state: FSMContext):
    plat=cb.data.replace("upd_script_","")
    await state.update_data(upd_platform=plat)
    await cb.message.edit_text(f"Platform: *{PLATFORMS[plat]['name']}*\n\nSend the new GAS script code as a text message.\n_(Paste the entire .gs file content)_",parse_mode="Markdown")
    await state.set_state(AdminSt.update_script_code); await cb.answer()

@router.message(AdminSt.update_script_code)
async def msg_script_code(msg: Message,state: FSMContext):
    await state.update_data(upd_code=msg.text)
    await msg.answer("Optional: add an *update note* for partners (or send `-` to skip):",parse_mode="Markdown")
    await state.set_state(AdminSt.update_script_note)

@router.message(AdminSt.update_script_note)
async def msg_script_note(msg: Message,state: FSMContext):
    data=await state.get_data()
    plat=data["upd_platform"]; code=data["upd_code"]
    note=None if msg.text.strip()=="-" else msg.text.strip()

    # Save to storage
    storage.set_platform_script(plat,code)

    # Push to all mother sheets of this platform
    pushed,failed=[],[]
    for sid,s in storage.all_mother_sheets().items():
        if s.get("platform")==plat:
            try:
                await asyncio.to_thread(gapi.push_library_code,s["script_id"],code)
                pushed.append(s["name"])
            except Exception as e: failed.append(f"{s['name']}: {e}")

    await msg.answer(f"✅ Script updated for *{PLATFORMS[plat]['name']}*\n\n"
                     f"Pushed to: {', '.join(pushed) or 'none'}\n"
                     f"Failed: {', '.join(failed) or 'none'}",
                     parse_mode="Markdown",reply_markup=kb_admin_home())

    # Notify partners
    affected=storage.all_child_sheets_for_platform(plat)
    notified_uids=set()
    for item in affected:
        uid=item["uid"]
        if uid in notified_uids: continue
        notified_uids.add(uid)
        partner=item["partner"]
        notify_text=(f"🔄 *Script Update — {PLATFORMS[plat]['name']}*\n\n"
                     f"Your analytics sheets have been updated with the latest script version.")
        if note: notify_text+=f"\n\n📝 *What's new:*\n{note}"
        try: await bot_instance.send_message(uid,notify_text,parse_mode="Markdown")
        except: pass

    await state.clear()

# ── FAQ update ────────────────────────────────────────────────
@router.callback_query(F.data=="adm_upd_faq")
async def cb_upd_faq(cb: CallbackQuery,state: FSMContext):
    if not storage.is_admin(cb.from_user.id): return await cb.answer("No access",show_alert=True)
    rows=[[_btn(p["name"],f"upd_faq_{k}")] for k,p in PLATFORMS.items()]
    rows.append([_btn("🌐 All Platforms","upd_faq_all"),_btn("❌ Cancel","cancel")])
    await cb.message.edit_text("Select platform for FAQ update:",reply_markup=_ik(*rows))
    await state.set_state(AdminSt.update_faq_platform); await cb.answer()

@router.callback_query(AdminSt.update_faq_platform,F.data.startswith("upd_faq_"))
async def cb_upd_faq_platform(cb: CallbackQuery,state: FSMContext):
    plat=cb.data.replace("upd_faq_","")
    await state.update_data(faq_platform=plat)
    await cb.message.edit_text("Send *FAQ content* as a text message:",parse_mode="Markdown")
    await state.set_state(AdminSt.update_faq_content); await cb.answer()

@router.message(AdminSt.update_faq_content)
async def msg_faq_content(msg: Message,state: FSMContext):
    data=await state.get_data(); plat=data["faq_platform"]; content=msg.text
    storage.set_platform_faq(plat,content)

    # Push FAQ to relevant mother sheets
    pushed=[]
    for sid,s in storage.all_mother_sheets().items():
        if plat=="all" or s.get("platform")==plat:
            try:
                await asyncio.to_thread(gapi.create_or_update_faq_sheet,sid,content)
                pushed.append(s["name"])
            except Exception as e: log.warning("FAQ push failed %s: %s",sid,e)

    await msg.answer(f"✅ FAQ updated!\nPushed to: {', '.join(pushed) or 'none'}",
                     parse_mode="Markdown",reply_markup=kb_admin_home())
    await state.clear()

# ── admin management ──────────────────────────────────────────
@router.callback_query(F.data=="adm_manage_admins")
async def cb_manage_admins(cb: CallbackQuery):
    if not storage.is_superadmin(cb.from_user.id): return await cb.answer("Superadmin only",show_alert=True)
    admins=storage.all_admins()
    lines=["👑 *Admins*\n"]
    for aid in admins: lines.append(f"  • `{aid}`")
    await cb.message.edit_text("\n".join(lines) or "No admins.",parse_mode="Markdown",
                               reply_markup=_ik([_btn("➕ Add Admin","adm_add_admin_btn")],
                                               [_btn("◀️ Back","adm_home")])); await cb.answer()

@router.callback_query(F.data=="adm_add_admin_btn")
async def cb_add_admin(cb: CallbackQuery,state: FSMContext):
    if not storage.is_superadmin(cb.from_user.id): return await cb.answer("Superadmin only",show_alert=True)
    await cb.message.edit_text("Enter *Telegram ID* of new admin:",parse_mode="Markdown")
    await state.set_state(AdminSt.add_admin_id); await cb.answer()

@router.message(AdminSt.add_admin_id)
async def msg_add_admin(msg: Message,state: FSMContext):
    try: uid=int(msg.text.strip())
    except ValueError: return await msg.answer("❌ Must be a number:")
    storage.add_admin(uid); await state.clear()
    await msg.answer(f"✅ Admin `{uid}` added!",parse_mode="Markdown",reply_markup=kb_admin_home())

# ── partner ───────────────────────────────────────────────────
@router.callback_query(F.data=="p_home")
async def cb_p_home(cb: CallbackQuery):
    p=storage.get_partner(cb.from_user.id)
    if not p: return await cb.answer("No access",show_alert=True)
    await cb.message.edit_text(f"🏠 *{p['name']}*",parse_mode="Markdown",reply_markup=kb_partner_home()); await cb.answer()

@router.callback_query(F.data=="p_create")
async def cb_p_create(cb: CallbackQuery,state: FSMContext):
    p=storage.get_partner(cb.from_user.id)
    if not p or not p.get("active"): return await cb.answer("Account not active",show_alert=True)
    if not storage.partner_assigned_sheets(cb.from_user.id): return await cb.answer("No sheets assigned — contact admin",show_alert=True)
    await cb.message.edit_text("Enter *advertiser name*\n_(e.g. FTD Gallery, 1xBet, etc.)_",parse_mode="Markdown")
    await state.set_state(PartnerSt.advertiser); await cb.answer()

@router.message(PartnerSt.advertiser)
async def msg_advertiser(msg: Message,state: FSMContext):
    advertiser=msg.text.strip()
    await state.update_data(advertiser=advertiser)
    sheets=storage.partner_assigned_sheets(msg.from_user.id)
    await msg.answer(f"Advertiser: *{advertiser}*\n\nNow select the *analytics platform*:",
                     parse_mode="Markdown",reply_markup=kb_select_mother(sheets))
    await state.set_state(PartnerSt.pick_mother)

@router.callback_query(PartnerSt.pick_mother,F.data.startswith("p_mother_"))
async def cb_pick_mother(cb: CallbackQuery,state: FSMContext):
    sid=cb.data.replace("p_mother_",""); mother=storage.get_mother_sheet(sid)
    if not mother: return await cb.answer("Not found",show_alert=True)
    p=storage.get_partner(cb.from_user.id)
    if sid not in p.get("assigned_sheet_ids",[]): return await cb.answer("No access",show_alert=True)
    plat_key=mother["platform"]
    data=await state.get_data()
    await state.update_data(mother_id=sid,platform_key=plat_key,config={})
    step=_next_step(plat_key,{})
    if step: await _send_step(cb,state,plat_key,{},step)
    else: await _show_confirm(cb,state)
    await cb.answer()

@router.callback_query(PartnerSt.config_step,F.data.startswith("fld_"))
async def cb_wizard(cb: CallbackQuery,state: FSMContext):
    raw=cb.data[4:]; sep=raw.index("__"); field=raw[:sep]; value=raw[sep+2:]
    data=await state.get_data(); config=data.get("config",{}); plat_key=data["platform_key"]
    # Handle skip
    if value=="SKIP": value=resolve_skip(field,plat_key)
    config[field]=value; await state.update_data(config=config)
    nxt=_next_step(plat_key,config)
    if nxt: await _send_step(cb,state,plat_key,config,nxt)
    else: await _show_confirm(cb,state)
    await cb.answer()

async def _show_confirm(cb,state):
    data=await state.get_data(); config=data.get("config",{})
    mother=storage.get_mother_sheet(data["mother_id"]); plat=PLATFORMS[data["platform_key"]]
    adv=data.get("advertiser","?")
    title=f"{adv} | {data.get('partner_name','?')} | Quality Analysis — EXTERNAL"
    lines="\n".join(f"  `{k}` → `{v}`" for k,v in config.items())
    await cb.message.edit_text(
        f"📋 *Confirm Sheet Creation*\n\nAdvertiser: *{adv}*\nPlatform: {plat['name']}\nSource: {mother['name']}\n"
        f"Library: `{plat['library_symbol']}`\n\nConfig:\n{lines}\n\nCreate?",
        parse_mode="Markdown",reply_markup=kb_confirm())
    await state.set_state(PartnerSt.confirm)

@router.callback_query(PartnerSt.confirm,F.data=="do_create")
async def cb_do_create(cb: CallbackQuery,state: FSMContext):
    data=await state.get_data(); p=storage.get_partner(cb.from_user.id)
    mother=storage.get_mother_sheet(data["mother_id"]); plat=PLATFORMS[data["platform_key"]]
    adv=data.get("advertiser","?")
    await cb.message.edit_text("⏳ Creating spreadsheet… (~30–60 sec)"); await cb.answer()
    try:
        child=await asyncio.to_thread(gapi.create_child_sheet,
                                       partner_name=p["name"],platform_key=data["platform_key"],
                                       mother=mother,config=data.get("config",{}),advertiser=adv)
        storage.add_child_sheet(cb.from_user.id,child)
        await cb.message.edit_text(
            f"✅ *Sheet ready!*\n\nAdvertiser: *{adv}*\n🔗 [Open Spreadsheet]({child['spreadsheet_url']})\n\n"
            f"Platform: {plat['name']}\nLibrary: `{plat['library_symbol']}`\n\n"
            f"_Paste raw data → {PLATFORMS[data['platform_key']]['raw_sheet']} tab → run 📊 ANALYSIS_",
            parse_mode="Markdown",reply_markup=kb_partner_home())
    except Exception as exc:
        log.exception("create_child_sheet failed")
        await cb.message.edit_text(f"❌ Failed.\n\n`{str(exc)[:400]}`\n\nContact admin.",parse_mode="Markdown",reply_markup=kb_partner_home())
    await state.clear()

@router.callback_query(F.data=="p_mysheets")
async def cb_mysheets(cb: CallbackQuery):
    p=storage.get_partner(cb.from_user.id)
    if not p: return await cb.answer("No access",show_alert=True)
    kids=p.get("child_sheets",[])
    if not kids: await cb.message.edit_text("No sheets yet.",reply_markup=kb_partner_home())
    else: await cb.message.edit_text(f"📋 *Your Sheets* ({len(kids)})",parse_mode="Markdown",reply_markup=kb_partner_sheets(kids))
    await cb.answer()

@router.callback_query(F.data.startswith("p_child_"))
async def cb_view_child(cb: CallbackQuery):
    sid=cb.data.replace("p_child_",""); p=storage.get_partner(cb.from_user.id)
    c=next((x for x in p.get("child_sheets",[]) if x["spreadsheet_id"]==sid),None)
    if not c: return await cb.answer("Not found",show_alert=True)
    plat=PLATFORMS.get(c.get("platform",""),{}); adv=c.get("advertiser","?")
    await cb.message.edit_text(
        f"📊 *{adv}* | {plat.get('name','?')}\nCreated: {c.get('created_at','')[:10]}\n\n🔗 [Open Spreadsheet]({c['spreadsheet_url']})",
        parse_mode="Markdown",reply_markup=_ik([_btn("◀️ Back","p_mysheets")])); await cb.answer()

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════
async def main():
    global storage,gapi,bot_instance
    assert BOT_TOKEN,"BOT_TOKEN env var is not set"
    storage=Storage(DATA_FILE)
    if FIRST_ADMIN_ID:
        storage._ensure_keys()
        if not storage._d.get("superadmin_id"): storage.set_superadmin(FIRST_ADMIN_ID)
        storage.add_admin(FIRST_ADMIN_ID)
    gapi=GoogleAPI()
    bot_instance=Bot(token=BOT_TOKEN)
    dp=Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    log.info("Bot v3 started")
    await dp.start_polling(bot_instance,allowed_updates=["message","callback_query"])

if __name__=="__main__":
    asyncio.run(main())
