-- local dir_to_num = { pz = 1, px = 2, nz = 3, nx = 4 }
local dir_to_num = { pz = 1, nx = 2, nz = 3, px = 4 }
local dir = dir_to_num[start_dir]

local function await_confirmation(message)
    print(message .. " Press C to continue and try again.")
    while true do
        local _, key = os.pullEvent("key")
        if key == keys.c then
            return
        end
    end
end

local function norm_delta(delta)
    while delta > 2 do
        delta = delta - 4
    end
    while delta < -2 do
        delta = delta + 4
    end
    return delta
end

local function clamp_dir()
    while dir < 1 do
        dir = dir + 4
    end
    while dir > 4 do
        dir = dir - 4
    end
end

local function face(target_dir)
    local delta = norm_delta(dir - dir_to_num[target_dir])
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
    clamp_dir()
end

local function move_up()
    while true do
        if turtle.up() then
            return
        end
        await_confirmation("Could not move up!")
    end
end

local function move_down()
    while true do
        if turtle.up() then
            return
        end
        await_confirmation("Could not move down!")
    end
end

local function right_direction(dx, dz)
    if dir == dir_to_num["px"] then
        return dx == 1
    elseif dir == dir_to_num["nx"] then
        return dx == -1
    elseif dir == dir_to_num["pz"] then
        return dz == 1
    elseif dir == dir_to_num["nz"] then
        return dz == -1
    end
end

local checked = { false, false, false, false }
local function __move_forward()
    while true do
        if turtle.forward() then
            return
        end
        await_confirmation("Could not move forward!")
    end
end
local function move_forward()
    if checked[dir] then
        __move_forward()
    else
        local sx, _, sz = gps.locate()
        __move_forward()
        local ex, _, ez = gps.locate()
        if not right_direction(ex - sx, ez - sz) then
            error("Turtle moved in the wrong direction! You either passed the wrong starting direction in or messed up your GPS configuration!")
        end
    end
end

local function move_to(x, y, z)
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
                move_up()
            end
        end
        if dy < 0 then
            for _ = 1, -dy do
                move_down()
            end
        end
        if dx > 0 then
            face("px")
            for _ = 1, dx do
                move_forward()
            end
        end
        if dx < 0 then
            face("nx")
            for _ = 1, -dx do
                move_forward()
            end
        end
        if dz > 0 then
            face("pz")
            for _ = 1, dz do
                move_forward()
            end
        end
        if dz < 0 then
            face("nz")
            for _ = 1, -dz do
                move_forward()
            end
        end
    end
end