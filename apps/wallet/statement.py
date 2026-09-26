"""Wallet statement PDF (contract 11.5)."""

import datetime as dt
import io

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import WalletTransaction
from .services import BALANCE_FILTER, get_wallet


def render_statement(user, start: dt.date, end: dt.date, lang: str) -> bytes:
    wallet = get_wallet(user)
    since = timezone.make_aware(dt.datetime.combine(start, dt.time.min))
    until = timezone.make_aware(dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min))
    rows = list(
        WalletTransaction.objects.filter(wallet=wallet, created_at__gte=since, created_at__lt=until)
        .select_related("pickup", "payout_method")
        .order_by("created_at")
    )
    opening = sum(
        t.amount
        for t in WalletTransaction.objects.filter(wallet=wallet, created_at__lt=since)
        .filter(BALANCE_FILTER)
        .only("amount")
    )

    # English labels: the bundled PDF fonts have no Devanagari glyphs.
    from .services import title

    styles = getSampleStyleSheet()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm)
    name = user.full_name or user.display_first_name or ""
    story = [
        Paragraph("Sajilo Kabadi — Wallet statement", styles["Title"]),
        Paragraph(f"{name} · {user.phone_masked}", styles["Normal"]),
        Paragraph(f"Period: {start.isoformat()} to {end.isoformat()}", styles["Normal"]),
        Spacer(1, 6 * mm),
    ]

    table = [["Date", "Description", "Ref", "Method", "Status", "Amount (Rs)", "Balance (Rs)"]]
    running = opening
    table.append(["", "Opening balance", "", "", "", "", f"{opening:,}"])
    for txn in rows:
        counts = txn.affects_balance and txn.status != WalletTransaction.Status.FAILED
        running += txn.amount if counts else 0
        table.append(
            [
                timezone.localtime(txn.created_at).strftime("%Y-%m-%d"),
                title(txn, "en"),
                txn.pickup.ref if txn.pickup_id else "",
                txn.method,
                txn.status,
                f"{txn.amount:+,}",
                f"{running:,}",
            ]
        )
    table.append(["", "Closing balance", "", "", "", "", f"{running:,}"])

    grid = Table(table, repeatRows=1, colWidths=[22 * mm, 48 * mm, 18 * mm, 16 * mm, 18 * mm, 24 * mm, 26 * mm])
    grid.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f5130")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("ALIGN", (5, 0), (-1, -1), "RIGHT"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#cccccc")),
                ("FONTNAME", (0, 1), (-1, 1), "Helvetica-Bold"),
                ("FONTNAME", (0, -1), (-1, -1), "Helvetica-Bold"),
            ]
        )
    )
    story.append(grid)
    doc.build(story)
    return buffer.getvalue()
