-- nexus_deploy.lua
-- Deploy a worker from a staging area to its assigned slice start using GPS.
-- Common tower transform comes from tower.cfg.
--
-- Usage:
--   nexus_deploy T01.plan
--
-- REQUIREMENTS:
-- * wireless modem + working ComputerCraft GPS
-- * turtle initially faces world +X (east) for this configured build
-- * staging path should be clear
-- * recommended staging Y >= 252 so deployment happens above the tower
--
-- The turtle navigates in WORLD coordinates to:
--   tower origin + plan OFFSET + (0,1,0)
-- It then writes nexus_gps.cfg for the builder.

local args={...}
if #args<1 then print("Usage: nexus_deploy <plan-file>"); return end
local planPath=args[1]
local TOWER="tower.cfg"
local GPSCFG="nexus_gps.cfg"

local ox,oy,oz,xvx,xvz,zvx,zvz
local offX,offY,offZ

local function parseTower()
  if not fs.exists(TOWER) then error("Missing "..TOWER) end
  local h=fs.open(TOWER,"r")
  while true do
    local l=h.readLine(); if not l then break end
    local a,b,c=string.match(l,"^origin=(%-?%d+) (%-?%d+) (%-?%d+)")
    if a then ox,oy,oz=tonumber(a),tonumber(b),tonumber(c) end
    local d,e=string.match(l,"^xvec=(%-?%d+) (%-?%d+)")
    if d then xvx,xvz=tonumber(d),tonumber(e) end
    local f,g=string.match(l,"^zvec=(%-?%d+) (%-?%d+)")
    if f then zvx,zvz=tonumber(f),tonumber(g) end
  end
  h.close()
  if not ox or not xvx or not zvx then error("Invalid tower.cfg") end
end

local function parsePlan()
  local h=fs.open(planPath,"r"); if not h then error("Missing "..planPath) end
  while true do
    local l=h.readLine(); if not l then break end
    local a,b,c=string.match(l,"^OFFSET (%-?%d+) (%-?%d+) (%-?%d+)")
    if a then offX,offY,offZ=tonumber(a),tonumber(b),tonumber(c) end
  end
  h.close()
  if offX==nil then error("Plan has no OFFSET") end
end

local function bootstrapFuel()
  local f=turtle.getFuelLevel()
  if f=="unlimited" or f>=500 then return end
  if turtle.getItemCount(16)==0 then error("Need fuel Ender Chest in slot 16") end
  if turtle.detectUp() then error("Need clear air above for fuel service") end
  turtle.select(16); assert(turtle.placeUp(),"Could not place fuel chest")
  turtle.select(8); local ok=turtle.suckUp(64)
  turtle.select(16); assert(turtle.digUp(),"Could not recover fuel chest")
  if not ok then error("Fuel chest empty") end
  turtle.select(8)
  while turtle.getItemCount(8)>0 and turtle.getFuelLevel()<12000 do
    assert(turtle.refuel(1),"Invalid fuel in slot 8")
  end
end

-- dir: 0 world +X, 1 world +Z, 2 world -X, 3 world -Z.
-- This deployment package intentionally uses the user's fixed +X/+Z orientation.
local dir=0
local function right() turtle.turnRight(); dir=(dir+1)%4 end
local function left() turtle.turnLeft(); dir=(dir+3)%4 end
local function face(d)
  local q=(d-dir)%4
  if q==1 then right() elseif q==2 then right();right() elseif q==3 then left() end
end
local function ensureFuel()
  local f=turtle.getFuelLevel()
  if f~="unlimited" and f<2500 then bootstrapFuel() end
end
local function stepForward()
  ensureFuel()
  if not turtle.forward() then error("Deployment path blocked in front.") end
end
local function stepUp()
  ensureFuel()
  if not turtle.up() then error("Deployment path blocked above.") end
end
local function stepDown()
  ensureFuel()
  if not turtle.down() then error("Deployment path blocked below.") end
end

parseTower(); parsePlan(); bootstrapFuel()

local sx,sy,sz=gps.locate(5)
if not sx then error("No GPS fix.") end
sx,sy,sz=math.floor(sx+0.5),math.floor(sy+0.5),math.floor(sz+0.5)

-- For configured xvec=(1,0), zvec=(0,1)
local tx=ox + offX*xvx + offZ*zvx
local tz=oz + offX*xvz + offZ*zvz
local ty=oy + offY + 1

print(("GPS start: %d %d %d"):format(sx,sy,sz))
print(("Assigned start: %d %d %d"):format(tx,ty,tz))
print("IMPORTANT: turtle must currently face world +X.")

-- Safe deployment strategy: horizontal first at current staging altitude,
-- then descend at the assigned slice start. Recommended staging is above tower.
if sx<tx then face(0); while sx<tx do stepForward(); sx=sx+1 end
elseif sx>tx then face(2); while sx>tx do stepForward(); sx=sx-1 end end

if sz<tz then face(1); while sz<tz do stepForward(); sz=sz+1 end
elseif sz>tz then face(3); while sz>tz do stepForward(); sz=sz-1 end end

while sy<ty do stepUp(); sy=sy+1 end
while sy>ty do stepDown(); sy=sy-1 end

face(0) -- builder starts local +X = world +X

local gx,gy,gz=gps.locate(5)
if not gx then error("Lost GPS at assigned start.") end
gx,gy,gz=math.floor(gx+0.5),math.floor(gy+0.5),math.floor(gz+0.5)
if gx~=tx or gy~=ty or gz~=tz then
  error(("Deployment GPS mismatch: expected %d %d %d got %d %d %d"):format(tx,ty,tz,gx,gy,gz))
end

local h=fs.open(GPSCFG,"w")
h.writeLine("plan="..planPath)
h.writeLine(("base=%d %d %d"):format(tx,ty-1,tz))
h.writeLine("xvec=1 0")
h.writeLine("zvec=0 1")
h.close()

print("DEPLOYMENT COMPLETE")
print(("At %d %d %d facing world +X"):format(tx,ty,tz))
print("GPS config written.")
print("Now run: nexus_builder_gps "..planPath)
