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
    while true do
        local cx, cy, cz = gps.locate()
        local dx = x - cx
        local dy = y - cy
        local dz = z - cz
        if dx == 0 and dy == 0 and dz == 0 then
            return
        end

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
end

function await_confirmation(message)
    print(message .. " Press C to continue and try again!")
    while true do
        local _, key = os.pullEvent("key")
        if key == keys.c then
            return
        end
    end
end

local curr_slot = 1
turtle.select(curr_slot)

function get_items_from_ender_chest()
    local done = false
    while not done do
        -- Check if chest is in slot 16
        turtle.select(16)
        if turtle.getItemCount(16) == 0 then
            await_confirmation("No chest in slot 16!")
        else
            -- Place chest below
            if not turtle.placeDown() then
                await_confirmation("Failed to place chest!")
            else
                -- Suck items from chest into slots 1-15
                for i = 1, 15 do
                    turtle.select(i)
                    while true do
                        if not turtle.suckDown() then
                            await_confirmation("No more items to suck!")
                        else
                            break
                        end
                    end
                end

                turtle.select(16)
                turtle.digDown()
                curr_slot = 1
                turtle.select(curr_slot)
                done = true
            end
        end
    end
end

function ensure_items_exist()
    if turtle.getItemCount(curr_slot) > 0 then
        return
    end

    while true do
        for slot = 1, 15 do
            if turtle.getItemCount(slot) > 0 then
                curr_slot = slot
                turtle.select(slot)
                return
            end
        end

        print("No items found, retrieving from chest")
        get_items_from_ender_chest()
    end
end

local all_data = {
    -- insert data here
}

local data = all_data[turtle_index]

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
