import asyncio
import logging

from yoomoney import AsyncClient

logger = logging.getLogger("frostrent.yoomoney_api")

POLL_INTERVAL = 15


async def check_payment_with_client(db, client: AsyncClient, payment_id: str):
    row = db.payment(payment_id)
    if not row:
        return False, None, None, "not_found"

    if row["status"] == "credited":
        return False, int(row["telegram_id"]), float(row["amount_rub"]), "already_credited"

    label = str(row["label"] or "").strip()
    if not label:
        return False, int(row["telegram_id"]), float(row["amount_rub"]), "missing_label"

    history = await client.operation_history(label=label, records=10)

    for op in history.operations:
        status = str(getattr(op, "status", "") or "")
        direction = str(getattr(op, "direction", "") or "")
        operation_type = str(getattr(op, "type", "") or "")
        operation_id = str(getattr(op, "operation_id", "") or "").strip()

        if status != "success" or direction != "in" or not operation_id:
            continue
        if operation_type not in {"deposition", "incoming-transfer"}:
            continue

        try:
            amount = round(float(getattr(op, "amount", 0) or 0), 2)
        except (TypeError, ValueError):
            continue

        ok, uid, credited_amount, reason = db.credit_payment_from_yoomoney(
            payment_id,
            amount,
            operation_id,
        )
        if ok:
            return True, uid, credited_amount, reason

        if reason in {"amount_mismatch", "duplicate_operation"}:
            return False, uid, credited_amount, reason

    return False, int(row["telegram_id"]), float(row["amount_rub"]), "not_paid"


async def check_payment_now(db, api_token: str, payment_id: str):
    async with AsyncClient(api_token) as client:
        return await check_payment_with_client(db, client, payment_id)


async def run_yoomoney_poller(db, settings, main_bot):
    token = str(settings.yoomoney_api_token or "").strip()
    if not token:
        logger.info("YooMoney API poller disabled: YOOMONEY_API_TOKEN is empty")
        return

    logger.info("YooMoney API poller started; interval=%ss", POLL_INTERVAL)

    try:
        async with AsyncClient(token) as client:
            while True:
                try:
                    rows = db.pending_payments(100)
                    for row in rows:
                        try:
                            ok, uid, amount, reason = await check_payment_with_client(
                                db, client, str(row["payment_id"])
                            )
                            if ok and uid:
                                try:
                                    await main_bot.send_message(
                                        uid,
                                        f"✅ Баланс пополнен: <b>+{amount:.2f} ₽</b>",
                                        parse_mode="HTML",
                                    )
                                except Exception:
                                    logger.exception(
                                        "Failed to notify user %s about YooMoney API credit",
                                        uid,
                                    )
                            elif reason not in {"not_paid", "already_credited"}:
                                logger.info(
                                    "YooMoney payment check payment=%s reason=%s",
                                    row["payment_id"],
                                    reason,
                                )
                        except Exception:
                            logger.exception(
                                "YooMoney API check failed for payment=%s",
                                row["payment_id"],
                            )
                except Exception:
                    logger.exception("YooMoney API poller iteration failed")

                await asyncio.sleep(POLL_INTERVAL)
    except asyncio.CancelledError:
        logger.info("YooMoney API poller stopped")
        raise
