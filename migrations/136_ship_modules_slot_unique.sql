-- One module per (ship, slot). `refit.install_module` replaces a slot's module, and the table had no
-- uniqueness to key that on: the earlier code named `ON CONFLICT (ship_id, slot_index)`, which raised
-- "no unique or exclusion constraint matching" after the treasury was already charged.
-- The code now runs UPDATE then INSERT inside one transaction and works without this index. The index
-- makes a concurrent double install fail loudly instead of leaving two rows in one slot.
--
-- NOT APPLIED. Remove duplicate (ship_id, slot_index) rows first: the CREATE fails while any exist.
-- Check: SELECT ship_id, slot_index, count(*) FROM maya_rp.ship_modules GROUP BY 1,2 HAVING count(*) > 1;
BEGIN;
SET search_path TO maya_rp;

CREATE UNIQUE INDEX IF NOT EXISTS ship_modules_ship_slot_key ON ship_modules (ship_id, slot_index);

COMMIT;
