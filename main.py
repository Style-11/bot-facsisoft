import logging
import json
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import pytz
import gspread
from google.oauth2.service_account import Credentials

# ── CONFIGURACIÓN ───────────────────────────────────────────

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")          # ID de tu Google Sheet
LIMA_TZ = pytz.timezone('America/Lima')

SISTEMAS = [
    "pickles",
    "pickles2",
    "floreriayregaloslaestacion",
    "worldfit360",
    "chifameilee",
    "multifarma",
    "feileng",
    "bijuki",
    "invydistribucionesfcp",
    "dimafer",
    "comercialyuly",
    "actecperu",
    "pichaywasy",
    "multiserviciosvirgendelpilarcruzate",
    "ottofriedrich",
    "tuseventosperu",
]

# ── CONEXIÓN GOOGLE SHEETS ──────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def conectar_sheets():
    """Conecta a Google Sheets. Usa env var GOOGLE_CREDENTIALS_JSON (Railway)
       o el archivo local JSON (desarrollo)."""
    creds_json = os.getenv("GOOGLE_CREDENTIALS_JSON")
    if creds_json:
        info = json.loads(creds_json)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    else:
        creds = Credentials.from_service_account_file(
            "bot-facsisoft-655f3545d3ba.json", scopes=SCOPES
        )
    client = gspread.authorize(creds)
    return client.open_by_key(GOOGLE_SHEET_ID).sheet1

sheet = None  # se inicializa en main

# ── ESTADO EN MEMORIA ───────────────────────────────────────

estado = {}

def ahora_lima():
    return datetime.now(LIMA_TZ)

def get_estado(sistema, fecha):
    return estado.get(sistema, {}).get(fecha.strftime('%Y-%m-%d'))

def set_estado(sistema, fecha, valor):
    if sistema not in estado:
        estado[sistema] = {}
    estado[sistema][fecha.strftime('%Y-%m-%d')] = valor

def icono(sistema, fecha):
    e = get_estado(sistema, fecha)
    return {"OK": "✅", "ER": "❌", "NA": "➖"}.get(e, "⬜")

def guardar_sheets(sistema, fecha_venta, estado_val):
    """Guarda o ACTUALIZA una fila en Google Sheets. No duplica, y mantiene orden."""
    global sheet
    ahora = ahora_lima()
    etiqueta = {"OK": "✅ Enviado Correcto", "ER": "❌ Error de Envío", "NA": "➖ No Aplica"}.get(estado_val, estado_val)
    fecha_venta_str = fecha_venta.strftime('%d/%m/%Y')
    fila_data = [sistema, ahora.strftime('%d/%m/%Y'), fecha_venta_str, ahora.strftime('%H:%M'), etiqueta]
    idx_sistema = SISTEMAS.index(sistema)

    try:
        all_values = sheet.get_all_values()

        # 1) ¿Ya existe esta combinación sistema+fecha? → Actualizar (corregir sin duplicar)
        for i, row in enumerate(all_values):
            if len(row) >= 3 and row[0] == sistema and row[2] == fecha_venta_str:
                sheet.update(f'A{i+1}:E{i+1}', [fila_data], value_input_option='USER_ENTERED')
                return True

        # 2) No existe → Insertar en posición ordenada por sistema
        filas_misma_fecha = []
        for i, row in enumerate(all_values[1:], start=2):  # skip header, 1-indexed
            if len(row) >= 3 and row[2] == fecha_venta_str:
                try:
                    idx_exist = SISTEMAS.index(row[0])
                    filas_misma_fecha.append((i, idx_exist))
                except ValueError:
                    pass

        if not filas_misma_fecha:
            # No hay filas para esta fecha → agregar al final
            sheet.append_row(fila_data, value_input_option='USER_ENTERED')
        else:
            # Buscar posición correcta dentro del bloque de esta fecha
            insertado = False
            for row_num, idx_exist in filas_misma_fecha:
                if idx_exist > idx_sistema:
                    sheet.insert_row(fila_data, row_num, value_input_option='USER_ENTERED')
                    insertado = True
                    break
            if not insertado:
                # Todos los existentes van antes → insertar después del último
                ultima = filas_misma_fecha[-1][0]
                sheet.insert_row(fila_data, ultima + 1, value_input_option='USER_ENTERED')

        return True
    except Exception as e:
        logging.error(f"Error al guardar en Sheets: {e}")
        return False

# ── INTERFAZ ────────────────────────────────────────────────

def ui_principal(fecha):
    hoy = ahora_lima()
    ok  = sum(1 for s in SISTEMAS if icono(s, fecha) == "✅")
    err = sum(1 for s in SISTEMAS if icono(s, fecha) == "❌")
    na  = sum(1 for s in SISTEMAS if icono(s, fecha) == "➖")
    pen = len(SISTEMAS) - ok - err - na

    texto = (
        f"📨 *RESÚMENES SUNAT — FacsiSoft*\n\n"
        f"📅 Registrando hoy *{hoy.strftime('%d/%m/%Y')}*\n"
        f"📦 Ventas del día: *{fecha.strftime('%d/%m/%Y')}*\n\n"
        f"✅ {ok}  ❌ {err}  ➖ {na}  ⬜ {pen}  — de {len(SISTEMAS)} sistemas\n\n"
        f"_Toca un sistema para registrar su estado_"
    )
    kb = [[
        InlineKeyboardButton("◀️", callback_data="atras"),
        InlineKeyboardButton(f"📅 {fecha.strftime('%d/%m/%Y')}", callback_data="noop"),
        InlineKeyboardButton("▶️", callback_data="adelante"),
    ]]
    for i, s in enumerate(SISTEMAS):
        kb.append([
            InlineKeyboardButton(f"{icono(s, fecha)} {s[:22]}", callback_data=f"s_{i}"),
            InlineKeyboardButton("🔗", url=f"https://{s}.sistematpv.com/summaries"),
        ])
    sheet_url = f"https://docs.google.com/spreadsheets/d/{GOOGLE_SHEET_ID}"
    kb.append([InlineKeyboardButton("📊 Ver Google Sheet", url=sheet_url)])
    return texto, InlineKeyboardMarkup(kb)

def ui_sistema(idx, fecha):
    hoy = ahora_lima()
    s = SISTEMAS[idx]
    e = get_estado(s, fecha) or "—"
    label = {"OK": "✅ Enviado Correcto", "ER": "❌ Error de Envío", "NA": "➖ No Aplica"}.get(e, "⬜ Sin registrar")
    texto = (
        f"🏪 *{s}*\n\n"
        f"📅 Registro: hoy *{hoy.strftime('%d/%m/%Y')}*\n"
        f"📦 Venta del: *{fecha.strftime('%d/%m/%Y')}*\n\n"
        f"Estado actual: {label}\n\n"
        f"_¿Qué estado tiene el resumen en FacsiSoft?_"
    )
    kb = [
        [InlineKeyboardButton("✅ Enviado Correcto",  callback_data=f"r_{idx}_OK")],
        [InlineKeyboardButton("❌ Error de Envío",     callback_data=f"r_{idx}_ER")],
        [InlineKeyboardButton("➖ No Aplica (sin boletas)", callback_data=f"r_{idx}_NA")],
        [InlineKeyboardButton("⬅️ Volver",             callback_data="main")],
    ]
    return texto, InlineKeyboardMarkup(kb)

# ── HANDLERS ────────────────────────────────────────────────

async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ayer = (ahora_lima() - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
    ctx.user_data['fecha'] = ayer
    texto, markup = ui_principal(ayer)
    await update.message.reply_text(texto, reply_markup=markup, parse_mode='Markdown')

async def on_click(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    d = q.data
    await q.answer()

    ahora = ahora_lima()
    fecha = ctx.user_data.get('fecha', (ahora - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0))

    if d == "noop":
        return

    elif d == "atras":
        fecha -= timedelta(days=1)
        ctx.user_data['fecha'] = fecha

    elif d == "adelante":
        fecha += timedelta(days=1)
        ctx.user_data['fecha'] = fecha

    elif d == "main":
        pass

    elif d.startswith("s_"):
        idx = int(d.split("_")[1])
        texto, markup = ui_sistema(idx, fecha)
        await q.edit_message_text(texto, reply_markup=markup, parse_mode='Markdown')
        return

    elif d.startswith("r_"):
        partes = d.split("_")
        idx, estado_val = int(partes[1]), partes[2]
        sistema = SISTEMAS[idx]
        set_estado(sistema, fecha, estado_val)
        if guardar_sheets(sistema, fecha, estado_val):
            await q.answer("✅ Guardado en Google Sheets.", show_alert=False)
        else:
            await q.answer("⚠️ Error al guardar. Reintenta.", show_alert=True)
        texto, markup = ui_principal(fecha)
        await q.edit_message_text(texto, reply_markup=markup, parse_mode='Markdown')
        return

    texto, markup = ui_principal(fecha)
    try:
        await q.edit_message_text(texto, reply_markup=markup, parse_mode='Markdown')
    except Exception:
        pass

# ── MAIN ────────────────────────────────────────────────────

if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

    # Conectar a Google Sheets y crear encabezados si la hoja está vacía
    sheet = conectar_sheets()
    if not sheet.row_values(1):
        sheet.append_row(["Sistema", "Fecha de Registro", "Fecha de Venta", "Hora", "Estado"])
    logging.info("✅ Conectado a Google Sheets correctamente.")

    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_click))
    logging.info("🤖 Bot iniciado. Esperando mensajes...")
    app.run_polling()