import logging
import pandas as pd
import os
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
from datetime import datetime, timedelta
import pytz

TOKEN = '7961458006:AAGqBIdJVm7pIQG7XaPIpPmiPE-sD5QwT88'
EXCEL_FILE = 'resumenes_sunat.xlsx'
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

# estado en memoria: estado[sistema][fecha_iso] = "OK" | "ER" | "NA" | None
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

def guardar_excel(sistema, fecha_resumen, estado_val):
    ahora = ahora_lima()
    fila = {
        'Sistema':           sistema,
        'Fecha de Envío':    ahora.strftime('%d/%m/%Y'),        # día que enviaste el resumen
        'Fecha de Proceso':  fecha_resumen.strftime('%d/%m/%Y'), # día de las ventas resumidas
        'Hora de Registro':  ahora.strftime('%H:%M'),
        'Estado':            {"OK": "✅ Enviado Correcto", "ER": "❌ Error de Envío", "NA": "➖ No Aplica"}.get(estado_val, estado_val),
        'URL Resúmenes':     f"https://{sistema}.sistematpv.com/summaries",
    }
    try:
        if os.path.exists(EXCEL_FILE):
            df = pd.read_excel(EXCEL_FILE)
        else:
            df = pd.DataFrame()
        df = pd.concat([df, pd.DataFrame([fila])], ignore_index=True)
        df.to_excel(EXCEL_FILE, index=False)
        return True
    except PermissionError:
        return False

# ── INTERFAZ ────────────────────────────────────────────────

def ui_principal(fecha):
    ok  = sum(1 for s in SISTEMAS if icono(s, fecha) == "✅")
    err = sum(1 for s in SISTEMAS if icono(s, fecha) == "❌")
    pen = len(SISTEMAS) - ok - err - sum(1 for s in SISTEMAS if icono(s, fecha) == "➖")

    texto = (
        f"📨 *RESÚMENES SUNAT*\n\n"
        f"📅 Resumen del día: *{fecha.strftime('%d/%m/%Y')}*\n\n"
        f"✅ {ok}  ❌ {err}  ⬜ {pen}  de {len(SISTEMAS)} sistemas\n\n"
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
    kb.append([InlineKeyboardButton("📊 Descargar Excel", callback_data="excel")])
    return texto, InlineKeyboardMarkup(kb)

def ui_sistema(idx, fecha):
    s = SISTEMAS[idx]
    e = get_estado(s, fecha) or "—"
    label = {"OK": "✅ Enviado Correcto", "ER": "❌ Error de Envío", "NA": "➖ No Aplica"}.get(e, "⬜ Sin registrar")
    texto = (
        f"🏪 *{s}*\n"
        f"📅 Resumen del: *{fecha.strftime('%d/%m/%Y')}*\n\n"
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
    # Por defecto: resumen del día anterior
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
        pass  # cae al render del menú

    elif d == "excel":
        if os.path.exists(EXCEL_FILE):
            await q.message.reply_document(document=open(EXCEL_FILE, 'rb'), caption="📊 Historial de resúmenes SUNAT.")
        else:
            await q.message.reply_text("⚠️ Aún no hay nada guardado.")
        return

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
        if guardar_excel(sistema, fecha, estado_val):
            await q.answer("✅ Guardado.", show_alert=False)
        else:
            await q.message.reply_text("⚠️ ¡Cierra el Excel, está abierto!")
        # Volver al menú principal
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
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CallbackQueryHandler(on_click))
    app.run_polling()