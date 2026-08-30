MANA NEXUS V5 - COMMON ORIGIN + GPS AUTO-DEPLOY
================================================

FIXED TOWER TRANSFORM
---------------------
Bottom/front-left schematic origin:
  X=235 Y=60 Z=250

Orientation:
  schematic +X -> world +X
  schematic +Z -> world +Z

Therefore the 111 x 111 footprint spans:
  world X 235..345
  world Z 250..360

The 191-block schematic height nominally spans:
  world Y 60..250

COMMON STAGING-LINE WORKFLOW
----------------------------
You no longer manually place each turtle at its slice.

Every worker gets:
  tower.cfg
  nexus_deploy.lua
  nexus_builder_gps.lua
  nexus_status.lua
  its own Txx.plan

Put the turtles in a convenient line OUTSIDE/ABOVE the tower footprint.
For the first test, staging them above Y=251 is strongly recommended so their
horizontal deployment paths cannot collide with the tower.

IMPORTANT CURRENT ASSUMPTION:
Before running nexus_deploy, every turtle must face WORLD +X (east).
This is intentional for the first reliable test because the tower orientation
is already fixed to +X/+Z.

Run on T01:
  nexus_deploy T01.plan

The turtle:
1. reads the shared tower origin,
2. reads OFFSET from its own plan,
3. gets its live GPS position,
4. navigates horizontally at staging altitude to its assigned X/Z,
5. descends/ascends to Y=61,
6. faces world +X,
7. verifies GPS,
8. writes nexus_gps.cfg.

Then run:
  nexus_builder_gps T01.plan

After T01 proves deployment/build/resume works, test T01 and T02 together.

ASSIGNED BUILD STARTS
---------------------
T01: world start (235, 61, 250)  schematic X 0..22  blocks=23193
T02: world start (258, 61, 250)  schematic X 23..29  blocks=21444
T03: world start (265, 61, 250)  schematic X 30..37  blocks=22816
T04: world start (273, 61, 250)  schematic X 38..47  blocks=23970
T05: world start (283, 61, 250)  schematic X 48..55  blocks=23989
T06: world start (291, 61, 250)  schematic X 56..62  blocks=19515
T07: world start (298, 61, 250)  schematic X 63..72  blocks=23970
T08: world start (308, 61, 250)  schematic X 73..80  blocks=22816
T09: world start (316, 61, 250)  schematic X 81..87  blocks=21444
T10: world start (323, 61, 250)  schematic X 88..110  blocks=23193

NOTE ON 'FRONT LEFT'
--------------------
This package treats (235,60,250) as exact schematic (0,0,0).
All block targets are transformed from that common origin.

SAFETY
------
The build runtime still:
- GPS verifies at startup and every 100 moves.
- Tracks local XYZ/facing.
- Persists progress.
- Enforces each worker's local slice bounds.
- Auto-restocks materials/fuel.
- Tracks deployed Ender Chest service transactions.

The deploy script itself currently assumes a clear path. It HALTS if blocked;
it does not dig through terrain or other turtles.
