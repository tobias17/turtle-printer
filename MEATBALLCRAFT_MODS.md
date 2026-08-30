# MeatballCraft mods — building block reference

We're playing **MeatballCraft: Dimensional Ascension** (1.12.2 expert tech-RPG
pack, 350+ mods — [repo](https://github.com/sainagh/meatballcraft),
[CurseForge](https://www.curseforge.com/minecraft/modpacks/meatballcraft)).
This is a reference for what extra blocks are actually available to build
with beyond vanilla, organized by what they're good for. Useful when
expanding `generate/islands/` theme palettes (`BLOCK_COLORS` dicts) or
designing the tree/spire — pick real block IDs from here rather than
inventing vanilla-only palettes.

Not verified against the pack's actual `mods/` folder or in-game — this is
built from the modlist plus general knowledge of each mod's 1.12.2 block
sets. Double check an exact block ID/registry name in-game (F3+H tooltips or
JEI) before using it in a generator script.

## General-purpose decorative block mods (biggest palette expansion)

- **Chisel** — the single largest source of building blocks in the pack:
  400+ decorative variants across families like Marble, Limestone,
  Andesite, Basalt, Obsidian bricks, Bloodstone, Antiblock, Tyrian,
  Chocolate(!), Frost/Icestone, Netherbrick, Enderstone, Redrock. Most
  support connected textures (CTM) and come in brick/tile/pillar/cobble
  sub-variants. Good for almost any theme that needs more than 2-3 flat
  colors without going full "noise" (see `AGENTS.md` rule 3 — still pick
  one or two Chisel variants deliberately, don't randomize across the set).
- **UnlimitedChiselWorks** — adds further chisel groups (more stone/wood
  variety) on top of base Chisel, same connected-texture family style.
- **Blockcraftery** — "framed" blocks: full cubes, stairs, slabs, walls,
  slants, and slant corners that take on any other block's texture via
  right-click, including reinforced (explosion/fire-proof) variants and a
  glowstone-lit variant. Useful less for palette variety and more for
  getting slab/stair/wall *shapes* out of any block we've already chosen.
- **ArchitectureCraft** — proper architectural geometry, not just textures:
  sloped roofs, glazable window frames, arches, round pillars/posts, rounded
  wall corners, classical entablature pieces, balcony/stair railings, plus
  slabs and stairs — all craftable from almost any base material (vanilla or
  modded). This is the mod to reach for if a theme ever needs actual
  sloped/arched geometry instead of a voxel approximation (e.g. `ruins.py`
  pillars, `gearworks.py` structural framing).
- **CTM (Connected Textures Mod)** — library mod; not blocks itself, but
  what gives Chisel/other mods their seamless connected-texture look. No
  direct action needed, just context for why some blocks blend at edges.
- **MalisisBlocks** — a "block mixer" that blends two different blocks
  together face-to-face (one texture on one side, blending into the other),
  plus vanishing/fade frames. Could be a shortcut for a clean gradient band
  between two solid materials instead of hand-picking an intermediate color.
- **MalisisDoors** — animated custom doors (glass, jail, factory, garage,
  sliding) if any build ever wants entrances beyond vanilla doors.

## Themed dimension / RPG mods (thematic block sets, good per-island-theme fits)

These mods each bring a cohesive aesthetic block set tied to their own
dimension or mob theme — good source material for specific island themes:

- **BiomesOPlenty** — huge stock of extra wood types, stone types (e.g.
  White Sandstone, Mud, Ash), and plant/leaf variety. Good general filler
  for `grass.py`, `desert.py`, `swamp.py`.
- **Natura** — more tree/wood variants (Redwood, Eucalyptus, Sakura, etc.)
  and Netherrack-like blocks; useful for `grass.py` top decoration or a
  `swamp.py`/jungle-leaning theme.
- **Botania** — "living" nature blocks (Livingrock, Livingwood, Dreamwood,
  Manasteel-adjacent decorative blocks) plus a wide range of clean colored
  stone-like blocks. Fits a magic/fantasy-leaning theme.
- **Astral Sorcery** — Marble family (its own, distinct from Chisel's) plus
  starlight-infused glowing blocks (Illumination Wand, Celestial Collector
  aesthetics). Good source for pale/glowing accents — could suit
  `crystal.py` or `snow.py` accents.
- **Thaumcraft** — Arcane Stone (worn/cracked stone bricks), Greatwood /
  Silverwood logs, Eldritch/Warped blocks from the endgame areas. Fits a
  spooky/arcane theme (`ruins.py`, `bones.py`).
- **TheBetweenlands** — swamp-dimension blocks: Rotten Bark, Weedwood,
  Sludge, Scabyst, Octine — a whole cohesive bog aesthetic. Direct fit for
  `swamp.py`.
- **AbyssalCraft** — dark/abyssal stone and brick sets (Coralium, Dread
  blocks), fits corrupted/dark themes — a candidate to strengthen
  `bones.py` or `ruins.py`.
- **Aether** — Holystone, Ambrosium, Skyroot wood, Aetherium — bright
  cloud-dimension palette; would suit a light/floating "heaven" style theme
  if one gets added.
- **TwilightForest** — its own stone/wood set (Twilight Oak, Time-worn/
  Mossy variants, Fiery blocks from the Fire dimension) — usable for a
  mossy-ruins or fire-adjacent theme (`ruins.py`, `volcano.py`).
- **IceAndFireRotN** — dragon-den themed blocks (Sculptable stone,
  dragonbone-ish decor) — direct relevance to `bones.py`.
- **DivineRPG / Erebus / Alfheim** — each add their own large ore/stone
  block sets tied to their custom dimensions; less individually documented
  but worth a JEI browse if a theme needs an exotic alien/insect look
  (`Erebus` is bug/hive themed — worth checking directly against `hive.py`).
- **Railcraft** — worth a mention for its iron/steel tank and reinforced
  block aesthetic (strongboxes, iron-clad blocks) — could suit
  `gearworks.py`'s industrial framing alongside the tech mods below.

## Tech-mod structural/industrial blocks (fits `gearworks.py`)

The pack's tech mods (Immersive Engineering, Thermal Expansion/Foundation,
EnderIO, Industrial Foregoing, Applied Energistics 2, RFTools, Draconic
Evolution, Extreme Reactors, TechReborn) all ship non-functional structural
variants alongside their machines — worth checking each mod's block list in
JEI for:

- **Immersive Engineering** — Concrete (multiple tints), Hempcrete, Treated
  Wood scaffolding/posts, Steel scaffolding, Blastproof blocks, Coke Bricks
  — probably the single best fit for `gearworks.py`'s industrial/riveted
  look.
- **EnderIO** — Dark Steel blocks, reinforced/obsidian-alloy blocks, Silent
  variants.
- **Draconic Evolution** — Draconium/Awakened Draconium blocks, Chaotic
  blocks — glowing high-tier accent material.
- **RFTools** — a range of clean colored "dimension building" blocks
  originally meant for pocket-dimension construction, good flat-color
  filler.

## Building/placement *tools* (not blocks, but relevant to construction)

- **BuildingGadgets** — copy/paste and beam-build large structures from an
  inventory of blocks. Not a block source, but relevant if we ever move from
  "generate a schematic" to "actually place this in survival."
- **BetterBuildersWands** (+ Fix) — extends a placed block along a line/
  plane, vanilla-style builder's wand improved.
- **ScaffoldingBackported** — vanilla-style scaffolding block, useful for
  in-progress builds, not part of any finished palette.

## Smaller/single-purpose block mods

- **Megelium Blocks** — one very tough, explosion-resistant block + matching
  glass pane and a "Megelium Stone" ore-in-stone variant. Niche, but a
  candidate for a "reinforced core" accent block if a theme wants one
  clearly indestructible-looking material (e.g. a `gearworks.py` core).
- **StorageDrawers / IronChest / BiblioCraft** — storage-furniture blocks
  (drawers, chests, bookshelves/display cases). Not palette material, but
  good if any build includes functional storage rooms.
- **Tardis** — Police Box and associated sci-fi console-room blocks, only
  relevant for a novelty build, not a theme palette.

## Sources

- [meatballcraft repo modlist](https://github.com/sainagh/meatballcraft)
- [MeatballCraft wiki](https://meatballcraft.miraheze.org/wiki/MeatballCraft:_Dimensional_Ascension)
- [CurseForge modpack page](https://www.curseforge.com/minecraft/modpacks/meatballcraft)
- [Chisel — FTB Wiki](https://ftb.fandom.com/wiki/Chisel_(mod))
- [ArchitectureCraft — CurseForge](https://www.curseforge.com/minecraft/mc-mods/architecturecraft)
- [Blockcraftery — CurseForge](https://www.curseforge.com/minecraft/mc-mods/blockcraftery)
- [MalisisBlocks / MalisisDoors — Minecraft Forum](https://www.minecraftforum.net/forums/mapping-and-modding-java-edition/minecraft-mods/2558284-malisisblocks-1-12-2-6-1-0-1-11-2-5-1-0-01-02-2018)
- [Megelium Blocks — CurseForge](https://www.curseforge.com/minecraft/mc-mods/megelium-blocks)
