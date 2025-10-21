--ARGS--

--CORE-LIB--

local curr_slot = 1
turtle.select(curr_slot)

local function get_items_from_ender_chest()
    local done = false
    while not done do
        -- Check if chest is in slot 16
        turtle.select(16)
        if turtle.getItemCount(16) == 0 then
            await_confirmation("No chest in slot 16!")
        else
            -- Place chest below
            if not turtle.placeUp() then
                await_confirmation("Failed to place chest!")
            else
                -- Suck items from chest into slots 1-15
                for i = 1, 15 do
                    turtle.select(i)
                    while true do
                        if not turtle.suckUp() then
                            await_confirmation("No more items to suck!")
                        else
                            break
                        end
                    end
                end

                turtle.select(16)
                turtle.digUp()
                curr_slot = 1
                turtle.select(curr_slot)
                done = true
            end
        end
    end
end

local function ensure_items_exist()
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

        print("No items found, retrieving from ender chest.")
        get_items_from_ender_chest()
    end
end

--DATA--

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
print("All done!")
