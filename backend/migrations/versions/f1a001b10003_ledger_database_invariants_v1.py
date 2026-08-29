"""ledger database invariants v1

Revision ID: f1a001b10003
Revises: f1a001b10002
"""

from alembic import op


revision = "f1a001b10003"
down_revision = "f1a001b10002"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE OR REPLACE FUNCTION
        khan_finance_validate_ledger_transaction()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_transaction_id uuid;
            v_transaction_currency varchar(3);
            v_entry_count bigint;
            v_debit_total bigint;
            v_credit_total bigint;
            v_currency_mismatch bigint;
        BEGIN
            IF TG_TABLE_NAME = 'ledger_transactions' THEN
                v_transaction_id := NEW.id;
            ELSE
                v_transaction_id := NEW.transaction_id;
            END IF;

            SELECT currency
              INTO v_transaction_currency
              FROM ledger_transactions
             WHERE id = v_transaction_id;

            IF v_transaction_currency IS NULL THEN
                RAISE EXCEPTION
                    'KF-001 ledger invariant: transaction does not exist';
            END IF;

            SELECT
                count(*),
                COALESCE(
                    sum(
                        CASE
                            WHEN side = 'debit'
                            THEN amount_minor
                            ELSE 0
                        END
                    ),
                    0
                ),
                COALESCE(
                    sum(
                        CASE
                            WHEN side = 'credit'
                            THEN amount_minor
                            ELSE 0
                        END
                    ),
                    0
                )
              INTO
                v_entry_count,
                v_debit_total,
                v_credit_total
              FROM ledger_entries
             WHERE transaction_id = v_transaction_id;

            IF v_entry_count < 2 THEN
                RAISE EXCEPTION
                    'KF-001 ledger invariant: transaction requires at least two entries';
            END IF;

            IF v_debit_total <> v_credit_total THEN
                RAISE EXCEPTION
                    'KF-001 ledger invariant: debits must equal credits';
            END IF;

            SELECT count(*)
              INTO v_currency_mismatch
              FROM ledger_entries le
              JOIN financial_accounts fa
                ON fa.id = le.account_id
             WHERE le.transaction_id = v_transaction_id
               AND fa.currency <> v_transaction_currency;

            IF v_currency_mismatch <> 0 THEN
                RAISE EXCEPTION
                    'KF-001 ledger invariant: entry account currency mismatch';
            END IF;

            RETURN NEW;
        END;
        $$;
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
        trg_ledger_transaction_balanced
        AFTER INSERT ON ledger_transactions
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
        khan_finance_validate_ledger_transaction();
        """
    )

    op.execute(
        """
        CREATE CONSTRAINT TRIGGER
        trg_ledger_entry_balanced
        AFTER INSERT ON ledger_entries
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW
        EXECUTE FUNCTION
        khan_finance_validate_ledger_transaction();
        """
    )


def downgrade():
    op.execute(
        """
        DROP TRIGGER IF EXISTS
        trg_ledger_entry_balanced
        ON ledger_entries;
        """
    )

    op.execute(
        """
        DROP TRIGGER IF EXISTS
        trg_ledger_transaction_balanced
        ON ledger_transactions;
        """
    )

    op.execute(
        """
        DROP FUNCTION IF EXISTS
        khan_finance_validate_ledger_transaction();
        """
    )
