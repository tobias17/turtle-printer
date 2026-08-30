-- nexus_resume_preflight.lua
-- Read-only safety check before resuming a Nexus builder.
-- It does NOT move/turn the turtle, modify builder state, or consume fuel.

local STATE="nexus_builder.state"
local CFG="nexus_gps.cfg"
local SERVICE="nexus_service.state"
local ok=true

local function fail(msg) print("FAIL: "..msg); ok=false end
local function pass(msg) print(" OK : "..msg) end

print("=== Nexus Resume Preflight ===")

if fs.exists(STATE) then
  local h=fs.open(STATE,"r")
  local plan=h.readLine() or "?"
  local processed=h.readLine() or "?"
  local pose=h.readLine() or "?"
  h.close()
  pass("Build state found")
  print("     Plan: "..plan)
  print("     Processed: "..processed)
  print("     Saved local pose: "..pose)
else
  fail("Missing nexus_builder.state -- do NOT resume as an existing build.")
end

if fs.exists(CFG) then pass("GPS config found") else fail("Missing nexus_gps.cfg") end

local gx,gy,gz=gps.locate(5)
if gx then
  pass(("GPS fix %.0f %.0f %.0f"):format(gx,gy,gz))
else
  fail("No GPS fix")
end

if fs.exists(SERVICE) then
  fail("nexus_service.state exists. A service chest may have been interrupted; inspect the block above the turtle before resuming.")
else
  pass("No interrupted service marker")
end

local function item(slot)
  local d=turtle.getItemDetail(slot)
  if not d then return "EMPTY" end
  return tostring(d.name).." x"..tostring(d.count or turtle.getItemCount(slot))
end

print("Fuel workspace slot 8:  "..item(8))
print("Fuel chest slot 16:     "..item(16))

if turtle.getItemCount(16)==0 then
  fail("Slot 16 is empty; put the FUEL Ender Chest there.")
else
  turtle.select(16)
  local isFuel=turtle.refuel(0)
  if isFuel then fail("Slot 16 contains fuel, not the fuel Ender Chest.") else pass("Slot 16 is not fuel") end
end

if turtle.getItemCount(8)>0 then
  turtle.select(8)
  local isFuel,reason=turtle.refuel(0)
  if isFuel then pass("Slot 8 contains valid fuel; patched builder can consume it safely")
  else fail("Slot 8 contains a non-fuel item: "..tostring(reason)) end
else
  pass("Slot 8 is empty")
end

print("Material chest slots 9-15:")
for s=9,15 do print(("  %2d: %s"):format(s,item(s))) end

print("Fuel:",tostring(turtle.getFuelLevel()),"/",tostring(turtle.getFuelLimit()))

if ok then
  print("PRECHECK PASSED")
  print("Safe to run the SAME nexus_builder_gps Txx.plan command without redeploying.")
else
  print("PRECHECK FAILED -- fix the items above before running the builder.")
end
