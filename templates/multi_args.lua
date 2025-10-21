local args = {...}
local turtle_index = tonumber(args[1])
local start_dir = args[2]
local start_layer = tonumber(args[3])
if not start_dir then
    print("Usage: program <turtle_index> <start_dir> [start_layer]")
    return
end
if not start_layer then
    start_layer = 1
end