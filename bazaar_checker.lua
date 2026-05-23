-- bazaar_checker.lua
-- Run with: /lua run bazaar_checker
-- Exports your trader inventory to a flat file for bazaar_checker.py
--
-- REQUIREMENTS:
--   1. Be in the bazaar zone
--   2. Be in trader mode (/trader)
--   MQ2Bzsrch and the Bazaar Search Window are handled automatically.

local mq = require('mq')

local SCRIPT_VERSION = "1.1.0"
local OUTPUT_FILE    = 'C:\\Users\\mjdei\\Desktop\\kreigar_inventory.txt'
local TRADER_NAME    = mq.TLO.Me.Name()

print("\atBazaar Checker v" .. SCRIPT_VERSION)
print("\atOriginally created by Alektra <Lederhosen>")

printf('\n[BazaarChecker] ========================================')
printf('[BazaarChecker] Trader Inventory Export for %s', TRADER_NAME)
printf('[BazaarChecker] ========================================')

-- Ensure MQ2Bzsrch is loaded
local pluginLoaded = mq.TLO.Plugin('MQ2Bzsrch').IsLoaded()
if not pluginLoaded then
    printf('[BazaarChecker] Loading MQ2Bzsrch...')
    mq.cmd('/plugin MQ2Bzsrch')
    mq.delay(2000)
    pluginLoaded = mq.TLO.Plugin('MQ2Bzsrch').IsLoaded()
    if not pluginLoaded then
        printf('[BazaarChecker] ERROR: Failed to load MQ2Bzsrch. Aborting.')
        return
    end
    printf('[BazaarChecker] MQ2Bzsrch loaded.')
end

-- Auto-open the Bazaar Search Window if it is not already open.
-- MQ2Bzsrch will crash the client if it fires a search with the window closed.
if not mq.TLO.Window('BazaarSearchWnd').Open() then
    printf('[BazaarChecker] Opening Bazaar Search Window...')
    mq.cmd('/bazaar')
    local waitMs      = 0
    local openTimeout = 5000
    while not mq.TLO.Window('BazaarSearchWnd').Open() and waitMs < openTimeout do
        mq.delay(100)
        waitMs = waitMs + 100
    end
    if not mq.TLO.Window('BazaarSearchWnd').Open() then
        printf('[BazaarChecker] ERROR: Bazaar Search Window did not open after %ds. Aborting.', openTimeout / 1000)
        return
    end
    printf('[BazaarChecker] Bazaar Search Window open.')
    mq.delay(250)  -- brief settle before searching
end

-- Reset any previous search results
mq.cmd('/breset')
mq.delay(500)

-- Run search filtered to this trader
printf('[BazaarChecker] Searching bazaar for trader: %s...', TRADER_NAME)
mq.cmdf('/bzsrch trader %s', TRADER_NAME)

-- Wait for search to complete
local searchTimeout = 10000
local elapsed       = 0
local interval      = 250
while not mq.TLO.Bazaar.Done() and elapsed < searchTimeout do
    mq.delay(interval)
    elapsed = elapsed + interval
end

if not mq.TLO.Bazaar.Done() then
    printf('[BazaarChecker] ERROR: Search timed out after %ds.', searchTimeout / 1000)
    return
end

local count = mq.TLO.Bazaar.Count()
printf('[BazaarChecker] Search complete. Found %d item(s).', count)

if count == 0 then
    printf('[BazaarChecker] No items found for %s. Are you in trader mode (/trader)?', TRADER_NAME)
    return
end

-- Write results to file.
-- MQ2Bzsrch Price is in copper (PGSC): 1 plat = 1000 copper.
-- Round to nearest plat so e.g. 1999cp -> 2pp.
local file, err = io.open(OUTPUT_FILE, 'w')
if not file then
    printf('[BazaarChecker] ERROR: Could not open output file: %s', tostring(err))
    return
end

local exported = 0
for i = 1, count do
    local item  = mq.TLO.Bazaar.Item(i)
    local name  = item.Name()
    local price = item.Price()  -- copper
    if name and price then
        local plat = math.floor((price + 500) / 1000)
        if plat < 1 then plat = 1 end
        file:write(string.format('%s|%d\n', name, plat))
        printf('[BazaarChecker]   %-40s %d pp', name, plat)
        exported = exported + 1
    end
end

file:close()

printf('\n[BazaarChecker] Exported %d item(s) to:', exported)
printf('[BazaarChecker]   %s', OUTPUT_FILE)
printf('[BazaarChecker] Now run:')
printf('[BazaarChecker]   python bazaar_checker.py --inventory "%s"', OUTPUT_FILE)
printf('[BazaarChecker] ========================================\n')
