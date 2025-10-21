local dir_to_num = { pz = 1, px = 2, nz = 3, nx = 4 }
local dir = dir_to_num[start_dir]

function await_confirmation(message)
    print(message .. " Press C to continue and try again!")
    while true do
        local _, key = os.pullEvent("key")
        if key == keys.c then
            return
        end
    end
end

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