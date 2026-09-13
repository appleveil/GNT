import logging

from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


@shared_task
def sweep_to_main_account(transaction_id):
    """
    Sweeps a Gaming Account deposit into the Main account via Paystack's Transfer
    API, per CONCEPT.md's "Platform rules > Deposits" flow (step: "Forward the
    payment — less transfer charges — to the main account").

    Runs async (not inline in the webhook view) so a slow/failing Paystack call
    never delays the webhook response Paystack is waiting on.

    Left as a stub: PAYSTACK_SECRET_KEY is empty until real sandbox keys exist,
    so there's nothing safe to call yet.
    """
    if not settings.PAYSTACK_SECRET_KEY:
        logger.info('Skipping Main account sweep for transaction %s — no Paystack key configured.', transaction_id)
        return

    # TODO: call Paystack's Transfer API to move the deposit (less transfer
    # charges) from the player's Gaming Account balance to the Main account,
    # then notify Cashier/Owner per the notification matrix (still open in
    # CONCEPT.md).
