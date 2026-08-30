-- nexus_builder_gps.lua
-- GPS-verified, bounded Mana Nexus worker.
-- Usage: nexus_builder_gps T01.plan

local args={...}
if #args<1 then print("Usage: nexus_builder_gps <plan-file>"); return end
local planPath=args[1]
local STATE="nexus_builder.state"
local CFG="nexus_gps.cfg"
local SERVICE="nexus_service.state"

local materialSlot={1,2,3,4,5,6,7}
local chestSlot={9,10,11,12,13,14,15}
local FUEL_LOW,FUEL_TARGET=2500,12000
local GPS_EVERY_MOVES=100

local x,y,z,dir=0,1,0,0
local processed,placed,skipped,moves=0,0,0,0
local minX,maxX,minY,maxY,minZ,maxZ
local baseX,baseY,baseZ,xvx,xvz,zvx,zvz

local function readCfg()
  if not fs.exists(CFG) then error("Missing "..CFG..". Run nexus_deploy first.") end
  local h=fs.open(CFG,"r")
  local cfgPlan=nil
  while true do
    local line=h.readLine(); if not line then break end
    local pp=string.match(line,"^plan=(.+)")
    if pp then cfgPlan=pp end
    local a,b,c=string.match(line,"^base=(%-?[%d%.]+) (%-?[%d%.]+) (%-?[%d%.]+)")
    if a then baseX,baseY,baseZ=tonumber(a),tonumber(b),tonumber(c) end
    local d,e=string.match(line,"^xvec=(%-?%d+) (%-?%d+)")
    if d then xvx,xvz=tonumber(d),tonumber(e) end
    local f,g=string.match(line,"^zvec=(%-?%d+) (%-?%d+)")
    if f then zvx,zvz=tonumber(f),tonumber(g) end
  end
  h.close()
  if not baseX or not xvx or not zvx then error("Invalid GPS config.") end
  if cfgPlan and cfgPlan~=planPath then
    error("GPS config belongs to "..cfgPlan..", not "..planPath)
  end
end

local function expectedWorld()
  return baseX+x*xvx+z*zvx, baseY+y, baseZ+x*xvz+z*zvz
end

local function gpsVerify()
  local gx,gy,gz=gps.locate(4)
  if not gx then error("GPS unavailable; halted safely.") end
  local ex,ey,ez=expectedWorld()
  if math.abs(gx-ex)>0.2 or math.abs(gy-ey)>0.2 or math.abs(gz-ez)>0.2 then
    error(("GPS MISMATCH expected %.0f %.0f %.0f got %.0f %.0f %.0f"):
      format(ex,ey,ez,gx,gy,gz))
  end
end

local function saveState()
  local h=fs.open(STATE,"w")
  h.writeLine(planPath)
  h.writeLine(tostring(processed))
  h.writeLine(("%d %d %d %d"):format(x,y,z,dir))
  h.writeLine(("%d %d %d"):format(placed,skipped,moves))
  h.close()
end

local function loadState()
  if not fs.exists(STATE) then return false end
  local h=fs.open(STATE,"r")
  local pp=h.readLine(); local pr=tonumber(h.readLine() or "0") or 0
  local pose=h.readLine() or ""; local st=h.readLine() or ""; h.close()
  if pp~=planPath then return false end
  local a,b,c,d=string.match(pose,"(%-?%d+) (%-?%d+) (%-?%d+) (%-?%d+)")
  local e,f,g=string.match(st,"(%d+) (%d+) (%d+)")
  if a then x,y,z,dir=tonumber(a),tonumber(b),tonumber(c),tonumber(d) end
  processed,placed,skipped,moves=pr,tonumber(e or 0),tonumber(f or 0),tonumber(g or 0)
  return true
end

local function markService(slot)
  local h=fs.open(SERVICE,"w"); h.writeLine(tostring(slot)); h.close()
end
local function clearService() if fs.exists(SERVICE) then fs.delete(SERVICE) end end
local function recoverInterrupted()
  if not fs.exists(SERVICE) then return end
  local h=fs.open(SERVICE,"r"); local slot=tonumber(h.readLine() or "0"); h.close()
  print("Recovering interrupted service chest to slot "..slot)

  if turtle.detectUp() then
    -- Never dig a service chest into an occupied recovery slot. Doing so can
    -- make the chest migrate to another inventory slot.
    if turtle.getItemCount(slot)>0 then
      error("Interrupted service chest is above turtle, but recovery slot "..slot.." is occupied. Clear that slot, then restart.")
    end
    turtle.select(slot)
    if not turtle.digUp() then error("Could not recover service chest.") end
  else
    print("No block above; clearing stale service marker.")
  end
  clearService()
end

local function deployAndPull(chestSlot,receiveSlot)
  if turtle.detectUp() then error("Service space above is blocked.") end
  if turtle.getItemCount(chestSlot)==0 then error("Missing Ender Chest slot "..chestSlot) end
  markService(chestSlot)
  turtle.select(chestSlot)
  if not turtle.placeUp() then clearService(); error("Could not place Ender Chest.") end
  turtle.select(receiveSlot); local ok=turtle.suckUp(64)
  turtle.select(chestSlot)
  if turtle.getItemCount(chestSlot)>0 then
    error("Recovery slot "..chestSlot.." became occupied while chest was deployed; halted before digging chest.")
  end
  if not turtle.digUp() then error("Could not recover Ender Chest.") end
  clearService()
  return ok
end

local function restockMaterial(k)
  if not deployAndPull(chestSlot[k],materialSlot[k]) or turtle.getItemCount(materialSlot[k])==0 then
    error("Material supply empty for palette "..k)
  end
end

local function consumeFuelWorkspace()
  -- Slot 8 is the fuel workspace. Consume anything already here BEFORE the
  -- fuel chest is placed. This prevents suckUp() from overflowing into the
  -- temporarily-empty slot 16 and displacing the fuel Ender Chest.
  turtle.select(8)
  while turtle.getItemCount(8)>0 and turtle.getFuelLevel()<FUEL_TARGET do
    local ok,err=turtle.refuel(1)
    if not ok then error("Slot 8 contains invalid fuel: "..tostring(err)) end
  end
end

local function pullFuelOnce()
  if turtle.getItemCount(8)>0 then
    error("Internal error: fuel workspace slot 8 must be empty before opening fuel chest.")
  end
  if turtle.detectUp() then error("Service space above is blocked.") end
  if turtle.getItemCount(16)==0 then error("Missing fuel Ender Chest in slot 16.") end

  markService(16)
  turtle.select(16)
  if not turtle.placeUp() then clearService(); error("Could not place fuel Ender Chest.") end

  -- Slot 8 is guaranteed empty here, so a full stack can fit without spilling
  -- into slot 16. CC:Tweaked suck starts at the selected slot and may continue
  -- into later acceptable slots if the selected slot lacks space.
  turtle.select(8)
  local ok=turtle.suckUp(64)

  -- Recover the chest while slot 16 is still guaranteed empty.
  turtle.select(16)
  if turtle.getItemCount(16)>0 then
    error("Fuel recovery slot 16 unexpectedly occupied; halted before digging chest.")
  end
  if not turtle.digUp() then error("Could not recover fuel Ender Chest.") end
  clearService()

  if not ok or turtle.getItemCount(8)==0 then error("Fuel supply empty.") end
end

local function refuel()
  if turtle.getFuelLevel()=="unlimited" then return end

  -- First use leftover fuel from the previous refill.
  consumeFuelWorkspace()
  if turtle.getFuelLevel()>=FUEL_TARGET then return end

  -- If the leftovers were insufficient, slot 8 is now empty. Pull a stack,
  -- recover the chest safely, then burn only what is needed to reach target.
  if turtle.getItemCount(8)>0 then
    error("Slot 8 still occupied below fuel target; check that it contains valid fuel.")
  end
  pullFuelOnce()
  consumeFuelWorkspace()

  if turtle.getFuelLevel()<FUEL_TARGET and turtle.getItemCount(8)==0 then
    -- Handles lower-energy fuels too; coal blocks normally reach target in one pull.
    pullFuelOnce()
    consumeFuelWorkspace()
  end
  if turtle.getFuelLevel()<FUEL_TARGET then
    error("Could not reach fuel target; fuel chest may be nearly empty.")
  end
end
local function ensureFuel()
  local f=turtle.getFuelLevel()
  if f~="unlimited" and f<FUEL_LOW then refuel() end
end

local function inBounds(nx,ny,nz)
  return nx>=minX and nx<=maxX and ny>=1 and ny<=maxY+1 and nz>=minZ and nz<=maxZ
end
local function postMove()
  moves=moves+1
  if moves%GPS_EVERY_MOVES==0 then gpsVerify() end
end

local function right() turtle.turnRight(); dir=(dir+1)%4 end
local function left() turtle.turnLeft(); dir=(dir+3)%4 end
local function face(d)
  local q=(d-dir)%4
  if q==1 then right() elseif q==2 then right(); right() elseif q==3 then left() end
end

local function forward()
  local nx,ny,nz=x,y,z
  if dir==0 then nx=nx+1 elseif dir==1 then nz=nz+1 elseif dir==2 then nx=nx-1 else nz=nz-1 end
  if not inBounds(nx,ny,nz) then error(("BOUNDARY VIOLATION -> %d %d %d"):format(nx,ny,nz)) end
  ensureFuel()
  if not turtle.forward() then error("Forward blocked; halted safely.") end
  x,y,z=nx,ny,nz; postMove()
end
local function up()
  if not inBounds(x,y+1,z) then error("BOUNDARY VIOLATION up") end
  ensureFuel(); if not turtle.up() then error("Up blocked.") end; y=y+1; postMove()
end
local function down()
  if not inBounds(x,y-1,z) then error("BOUNDARY VIOLATION down") end
  ensureFuel(); if not turtle.down() then error("Down blocked.") end; y=y-1; postMove()
end
local function moveX(tx)
  if tx>x then face(0); while x<tx do forward() end
  elseif tx<x then face(2); while x>tx do forward() end end
end
local function moveZ(tz)
  if tz>z then face(1); while z<tz do forward() end
  elseif tz<z then face(3); while z>tz do forward() end end
end
local function moveTo(tx,ty,tz)
  while y<ty do up() end
  while y>ty do down() end
  moveX(tx); moveZ(tz)
end

local function ensureMaterial(k)
  if turtle.getItemCount(materialSlot[k])==0 then restockMaterial(k) end
  turtle.select(materialSlot[k])
end

local function placeBlock(tx,ty,tz,k)
  moveTo(tx,ty+1,tz)
  ensureMaterial(k)
  if turtle.detectDown() then
    if turtle.compareDown() then skipped=skipped+1; return end
    error(("Wrong block at local %d %d %d"):format(tx,ty,tz))
  end
  if not turtle.placeDown() then error(("Placement failed at %d %d %d"):format(tx,ty,tz)) end
  placed=placed+1
end

local h=fs.open(planPath,"r"); if not h then error("Cannot open "..planPath) end
local lines={}
while true do local l=h.readLine(); if not l then break end; lines[#lines+1]=l end
h.close()

local total
for _,line in ipairs(lines) do
  local a,b,c,d,e,f=string.match(line,"^BOUNDS (%-?%d+) (%-?%d+) (%-?%d+) (%-?%d+) (%-?%d+) (%-?%d+)")
  if a then minX,maxX,minY,maxY,minZ,maxZ=tonumber(a),tonumber(b),tonumber(c),tonumber(d),tonumber(e),tonumber(f) end
  local n=string.match(line,"^BLOCKS (%d+)"); if n then total=tonumber(n) end
end
if not minX then error("Plan missing BOUNDS.") end

readCfg()
recoverInterrupted()
ensureFuel()
local resumed=loadState()
gpsVerify()

print(resumed and "RESUME" or "NEW BUILD",planPath)
print("Computer ID:",os.getComputerID())
print("Bounds X",minX,maxX,"Z",minZ,maxZ,"Y",maxY)
print("Blocks:",total,"GPS OK")

local seen=0
for _,line in ipairs(lines) do
  if string.sub(line,1,2)=="B " then
    seen=seen+1
    if seen>processed then
      local a,b,c,d=string.match(line,"^B (%-?%d+) (%-?%d+) (%-?%d+) (%d+)")
      placeBlock(tonumber(a),tonumber(b),tonumber(c),tonumber(d))
      processed=seen
      if processed%20==0 then saveState() end
      if processed%250==0 then
        print(("%d/%d placed=%d skipped=%d fuel=%s moves=%d"):
          format(processed,total,placed,skipped,tostring(turtle.getFuelLevel()),moves))
      end
    end
  end
end

saveState()
gpsVerify()
print("COMPLETE",planPath,"placed",placed,"skipped",skipped)
