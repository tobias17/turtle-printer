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

local dir_to_num = { pz = 1, px = 2, nz = 3, nx = 4 }
local dir = dir_to_num[start_dir]

function face(target_dir)
    local delta = dir - dir_to_num[target_dir]
    if delta > 2 then
        delta = delta - 4
    elseif delta < -2 then
        delta = delta + 4
    end
    while delta ~= 0 do
        if delta < 0 then
            turtle.turnRight()
            delta = delta + 1
            dir = dir + 1
        elseif delta > 0 then
            turtle.turnLeft()
            delta = delta - 1
            dir = dir - 1
        end
    end
    if dir < -2 then
        dir = dir + 4
    elseif dir > 2 then
        dir = dir - 4
    end
end

function move_to(x, y, z)
    local cx, cy, cz = gps.locate()
    local dx = x - cx
    local dy = y - cy
    local dz = z - cz
    print(dx .. ", " .. dy .. ", " .. dz)
    if dy > 0 then
        for _ = 1, dy do
            turtle.up()
        end
    end
    if dy < 0 then
        for _ = 1, -dy do
            turtle.down()
        end
    end
    if dx > 0 then
        face("px")
        for _ = 1, dx do
            turtle.forward()
        end
    end
    if dx < 0 then
        face("nx")
        for _ = 1, -dx do
            turtle.forward()
        end
    end
    if dz > 0 then
        face("pz")
        for _ = 1, dz do
            turtle.forward()
        end
    end
    if dz < 0 then
        face("nz")
        for _ = 1, -dz do
            turtle.forward()
        end
    end
end

local curr_slot = 1
turtle.select(curr_slot)
function ensure_items_exist()
    if turtle.getItemCount(curr_slot) > 0 then
        return
    end

    while true do
        for slot = 1, 16 do
            if turtle.getItemCount(slot) > 0 then
                curr_slot = slot
                turtle.select(slot)
                return
            end
        end

        print("No items found, put some in inventory and press c")
        while true do
            local event, key = os.pullEvent("key")
            if key == keys.c then
                break
            end
        end
    end
end

data = {
    -- insert data here
}

for y = 1, #data do
    if y < start_layer then
        print("Skipping layer: " .. y)
    else
        print("Starting layer: " .. y)
        for i = 1, #data[y] do
            print("Placing at: (" .. data[y][i][1] .. "," .. data[y][i][2] .. ")")
            move_to(data[y][i][1], y, data[y][i][2])
            ensure_items_exist()
            turtle.placeDown()
        end
    end
end
