local args = {...}
local start_dir = args[1]
local start_layer = tonumber(args[2])
if not start_dir then
    print("Usage: program <start_dir> [start_layer]")
    return
end
if not start_layer then
    start_layer = 1
end