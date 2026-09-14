"""
No Celery tasks needed here as of 2026-09-13.

sweep_to_main_account (queued from a DVA-deposit webhook) was retired: it
assumed each Gaming Account was a separate Paystack integration that needed
an explicit Transfer to move funds into the Main account. Under the actual
Paystack model (one integration; a Gaming Account is a Customer + Dedicated
Virtual Account) there is only one Paystack balance — a DVA deposit is
already in it the moment it clears, so there is nothing to sweep. See
payments/services.py's handle_charge_success and CONCEPT.md/SCHEMA.md.

Payout transfers (money actually leaving the club's Paystack balance) are
synchronous instead — see payments/services.py's initiate_payout_transfer,
called from gaming.services.approve_payout.
"""
