-- nexus_status.lua
if not fs.exists("nexus_builder.state") then
  print("No build state.")
else
  local h=fs.open("nexus_builder.state","r")
  print("Plan:",h.readLine())
  print("Processed:",h.readLine())
  print("Local pose x y z dir:",h.readLine())
  print("Placed skipped moves:",h.readLine())
  h.close()
end
print("Fuel:",tostring(turtle.getFuelLevel()),"/",tostring(turtle.getFuelLimit()))
local x,y,z=gps.locate(3)
if x then print(("GPS: %.0f %.0f %.0f"):format(x,y,z)) else print("GPS: NO FIX") end
