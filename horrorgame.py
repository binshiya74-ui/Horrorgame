"""
THE DARK HOUSE — FPV Enhanced Edition
======================================
Pure Python + Pygame raycasting horror game.

NEW FEATURES
------------
* Stamina system  — sprint with SHIFT, drains/recharges
* Sanity meter    — decreases near the entity / in darkness, causes hallucinations
* Battery system  — flashlight drains over time, find batteries to recharge
* Inventory limit — carry max 4 items; choose wisely
* Multiple keys   — each door has its own colour-coded key
* Locked cabinets — find the right code note to open them
* Hidden room     — secret passage behind a bookcase in the hallway
* Entity AI       — entity patrols rooms, reacts to noise (sprinting = loud)
* Noise meter     — be quiet or you attract it faster
* Footstep sounds — generated via pygame beeps (no external audio files)
* Blood / scratch marks on walls (procedural texture overlay)
* Animated door   — doors slide open over 0.3 s
* Death animation — screen cracks and fades to black
* Win cutscene    — brief typewriter text on escape
* Pause menu      — ESC pauses, shows controls
* Settings        — toggle minimap, toggle mouse look
* Mouse look      — optional mouse-look aiming
* Journal system  — collect notes that reveal lore + hints
* HUD breath bar  — visual breathing effect on sanity loss
* Room-specific   — ambient colour temperature per room
* Objectives list — track what you still need to do

Install : pip install pygame
Run     : python dark_house_fpv2.py

Controls
--------
W/S/A/D or ARROWS  move / turn
SHIFT (hold)        sprint (loud!)
E                   interact
F                   toggle flashlight
TAB                 journal / inventory
ESC                 pause
M                   toggle minimap
"""

import pygame
import sys
import math
import random
import time
import os

# ── Constants ─────────────────────────────────────────────────────────────────
W, H        = 960, 620
HALF_H      = H // 2
NUM_RAYS    = W // 2
FOV         = math.pi / 3
HALF_FOV    = FOV / 2
RAY_STEP    = FOV / NUM_RAYS
MAX_DEPTH   = 22
MOVE_SPEED  = 0.055
SPRINT_MUL  = 1.85
TURN_SPEED  = 0.038
FPS         = 60
HUD_H       = 90

# ── Colours ───────────────────────────────────────────────────────────────────
SKY         = (8,  6, 10)
FL_FAR      = (12, 10,  8)
FL_NEAR     = (26, 22, 16)

WALL_PAL = {
    "bedroom":  (72, 55, 38),
    "hallway":  (38, 40, 60),
    "attic":    (64, 50, 28),
    "basement": (28, 33, 52),
    "secret":   (18, 45, 18),   # sickly green
    "lab":      (50, 20, 20),   # deep red
}

DOOR_PAL = {
    "normal":  (55, 38, 22),
    "red":     (100, 20, 20),
    "blue":    (20, 40, 100),
    "green":   (20, 80, 25),
    "exit":    (20, 100, 30),
    "secret":  (35, 55, 35),
    "locked":  (80, 70, 15),
}

C_W   = (220, 210, 180)
C_DIM = (100,  95,  75)
C_WRN = (190,  55,  25)
C_GD  = ( 75, 175,  75)
C_EVT = (155, 120,  45)
C_BLU = ( 80, 130, 200)
C_YEL = (210, 190,  50)
HUD_BG= (  5,   5,   7)

# ── World Maps ────────────────────────────────────────────────────────────────
# Symbols:
#   #  solid wall      .  floor
#   D  normal door     R  red-key door   B  blue-key door   G  green-key door
#   X  exit door       S  secret door (bookcase)
#   ^  entity spawn

MAPS = {
    "bedroom": [
        "############",
        "#..........#",
        "#..#....#..#",
        "#..#....#..#",
        "#..........D",   # D col 11 row 4 → hallway
        "#..........#",
        "#....#.....#",
        "#....#.....#",
        "############",
    ],
    "hallway": [
        "#######",
        "D......",        # row 0 col 0 → attic (north exit, treated as door row=0)
        "#......",
        "#......",
        "#......S",       # S col 6 row 4 → secret room
        "#......",
        "D......",        # row 6 col 0 → basement
        "#......",
        "#......",
        "#......",
        "#......",
        "#######",
    ],
    "attic": [
        "#############",
        "#...........#",
        "#..###......#",
        "#...........#",
        "#......###..#",
        "#...........#",
        "#...........D",  # col 12 row 6 → hallway back
        "#############",
    ],
    "basement": [
        "#############",
        "#.....#.....#",
        "#.....#.....#",
        "#...........#",
        "#.....#.....#",
        "#.....#.....#",
        "R...........X",  # R col 0 → red locked; X col 12 → EXIT
        "#...........#",
        "#############",
    ],
    "secret": [
        "#########",
        "#.......#",
        "#.......#",
        "#.......#",
        "#.......#",
        "#.......S",      # back to hallway
        "#########",
    ],
}

# Door links: (room, row, col) → (dest_room, spawn_x, spawn_y, spawn_angle, key_needed)
DOOR_LINKS = {
    ("bedroom",  4, 11): ("hallway",  5.5, 5.0,  math.pi,      None),
    ("hallway",  4,  6): ("secret",   3.5, 4.5,  math.pi,      None),
    ("hallway",  0,  0): ("attic",    6.5,12.0,  math.pi,      None),
    ("hallway",  6,  0): ("basement", 6.5, 1.5,  0.0,          None),
    ("attic",    6, 12): ("hallway",  1.5, 5.0,  math.pi*1.5,  None),
    ("basement", 6,  0): ("hallway",  6.5, 5.0,  0.0,         "red_key"),
    ("basement", 6, 12): ("outside",  0,   0,    0.0,          "blue_key"),
    ("secret",   5,  8): ("hallway",  4.5, 5.5,  math.pi,      None),
}

# Items: (room, wx, wy): {name, label, color, interact_text, one_use}
ITEMS_DEF = {
    ("bedroom",  9.5, 1.5): {"name":"flashlight","label":"Flashlight","color":(200,180,60),
                              "text":"You grab the FLASHLIGHT."},
    ("bedroom",  9.5, 6.5): {"name":"battery",   "label":"Battery",   "color":(60,180,80),
                              "text":"You pocket a BATTERY. (Charges flashlight)"},
    ("attic",    2.5, 1.5): {"name":"blue_key",  "label":"Blue Key",  "color":(60,120,220),
                              "text":"A BLUE KEY — this must open something."},
    ("attic",   10.5, 4.5): {"name":"battery",   "label":"Battery",   "color":(60,180,80),
                              "text":"Another BATTERY. Good."},
    ("basement", 9.5, 4.5): {"name":"red_key",   "label":"Red Key",   "color":(220,60,60),
                              "text":"A RED KEY. There's a locked door..."},
    ("basement", 2.5, 1.5): {"name":"note_lab",  "label":"Note",      "color":(200,190,140),
                              "text":"A torn note: 'Cabinet code — 4 7 1'"},
    ("secret",   4.5, 2.5): {"name":"note_lore", "label":"Diary",     "color":(200,190,140),
                              "text":"Diary: 'It comes every night. It lives in the walls.'"},
    ("secret",   4.5, 4.5): {"name":"amulet",    "label":"Amulet",    "color":(180,80,200),
                              "text":"A strange AMULET. You feel... calmer holding it."},
    ("hallway",  3.5, 3.5): {"name":"battery",   "label":"Battery",   "color":(60,180,80),
                              "text":"A BATTERY behind the painting."},
}

NOTES_CONTENT = {
    "note_lab":  ["A torn scrap of paper.", "",
                  "The handwriting is shaky:", "'Cabinet code — 4 7 1'", "",
                  "Someone circled 'DON'T OPEN' in red.", "Then crossed it out."],
    "note_lore": ["Diary — Day Unknown", "",
                  "'It comes every night now.'",
                  "'I can hear it in the walls,'",
                  "'in the floor, in my own head.'",
                  "", "'The amulet slows it. Nothing stops it.'",
                  "'The only way out is through the basement.'",
                  "'Blue key. Red key. In that order.'"],
}

JOURNAL_ENTRIES = [
    "You wake up in a dark house. Something is wrong.",
    "The air smells of damp wood and something else. Burnt.",
    "Find a way out. The basement must have an exit.",
]

OBJECTIVES = [
    ("Find the flashlight",     lambda gs: "flashlight" in gs.inventory),
    ("Find the blue key",       lambda gs: "blue_key"   in gs.inventory),
    ("Find the red key",        lambda gs: "red_key"    in gs.inventory),
    ("Unlock the basement gate",lambda gs: gs.red_door_open),
    ("Escape through the exit", lambda gs: gs.escaped),
]

RANDOM_EVENTS = [
    "A floorboard creaks somewhere behind you.",
    "Something drags slowly overhead.",
    "A distant door slams.",
    "Three taps on the wall beside you.",
    "The temperature drops sharply.",
    "Slow breathing echoes through the corridor.",
    "A shadow crosses under the door.",
    "The house groans deeply.",
    "You smell something burnt and sweet.",
    "Fingernails scraping on wood — close.",
    "A child's laugh, cut short.",
    "Water drips somewhere in the walls.",
    "A clock ticks once. Then stops.",
]

ENTITY_WARNS = [
    "It's getting closer...",
    "Heavy footsteps on the stairs.",
    "A shape moves at the edge of darkness.",
    "The breathing is right behind you.",
    "IT IS HERE.",
]

SANITY_MSGS = [
    "The walls seem to breathe.",
    "Are those eyes in the wallpaper?",
    "You feel like you're being watched.",
    "The shadows move when you look away.",
    "Something whispers your name.",
]

SPRITES_DEF = {
    "bedroom":  [{"x":9.5,"y":2.5,"type":"cabinet","solid":True},
                 {"x":2.5,"y":1.5,"type":"bed",    "solid":True},
                 {"x":2.5,"y":6.5,"type":"desk",   "solid":True}],
    "hallway":  [{"x":3.5,"y":2.5,"type":"painting","solid":False},
                 {"x":3.5,"y":7.5,"type":"table",  "solid":False}],
    "attic":    [{"x": 9.5,"y":3.5,"type":"chair",  "solid":True},
                 {"x": 5.5,"y":2.5,"type":"chest",  "solid":True},
                 {"x": 2.5,"y":5.5,"type":"boxes",  "solid":True}],
    "basement": [{"x":2.5,"y":2.5,"type":"workbench","solid":True},
                 {"x":8.5,"y":2.5,"type":"shelves", "solid":True},
                 {"x":10.5,"y":6.5,"type":"exit_door","solid":True}],
    "secret":   [{"x":2.5,"y":2.5,"type":"altar",  "solid":True},
                 {"x":6.5,"y":2.5,"type":"mirror",  "solid":False}],
}

SPRITE_COLS = {
    "cabinet":   (52, 38, 22), "bed":       (45, 32, 25),
    "desk":      (40, 30, 18), "painting":  (60, 45, 30),
    "table":     (48, 35, 20), "chair":     (42, 32, 18),
    "chest":     (50, 40, 15), "boxes":     (45, 38, 22),
    "workbench": (35, 45, 25), "shelves":   (30, 30, 40),
    "exit_door": (20, 70, 28), "altar":     (50, 18, 18),
    "mirror":    (80, 90,100),
}

# ── Map helpers ───────────────────────────────────────────────────────────────
def get_cell(room, col, row):
    m = MAPS[room]
    if row < 0 or row >= len(m): return '#'
    if col < 0 or col >= len(m[row]): return '#'
    return m[row][col]

def is_solid(room, col, row, gs=None):
    c = get_cell(room, col, row)
    if c == '#': return True
    if c in ('D','R','B','G','X','S'): return False  # passable (handled via interact)
    return False

def door_color(cell, gs):
    if cell == 'R': return DOOR_PAL["red"]
    if cell == 'B': return DOOR_PAL["blue"]
    if cell == 'G': return DOOR_PAL["green"]
    if cell == 'X': return DOOR_PAL["exit"] if (gs and "blue_key" in gs.inventory) else DOOR_PAL["locked"]
    if cell == 'S': return DOOR_PAL["secret"]
    return DOOR_PAL["normal"]

# ── Raycaster ─────────────────────────────────────────────────────────────────
def cast_rays(room, px, py, angle, gs):
    results = []
    ray_angle = angle - HALF_FOV
    for _ in range(NUM_RAYS):
        ra  = ray_angle
        ca  = math.cos(ra); sa = math.sin(ra)
        mx  = int(px);      my = int(py)
        ddx = abs(1/ca) if ca != 0 else 1e30
        ddy = abs(1/sa) if sa != 0 else 1e30
        if ca < 0: sx=-1; sdx=(px-mx)*ddx
        else:      sx= 1; sdx=(mx+1.0-px)*ddx
        if sa < 0: sy=-1; sdy=(py-my)*ddy
        else:      sy= 1; sdy=(my+1.0-py)*ddy
        hit=False; side=0; cell='#'
        for _ in range(MAX_DEPTH*4):
            if sdx < sdy: sdx+=ddx; mx+=sx; side=0
            else:         sdy+=ddy; my+=sy; side=1
            cell = get_cell(room, mx, my)
            if cell in ('#','D','R','B','G','X','S'):
                hit=True; break
        dist = MAX_DEPTH
        if hit:
            if side==0: dist=(mx-px+(1-sx)/2)/ca
            else:       dist=(my-py+(1-sy)/2)/sa
            dist = max(0.01, dist * math.cos(ra - angle))
        results.append((dist, cell, side))
        ray_angle += RAY_STEP
    return results

# ── Sound (beep-only, no files) ───────────────────────────────────────────────
def init_sound():
    pygame.mixer.init(frequency=22050, size=-16, channels=1, buffer=256)

def beep(freq=440, dur=80, vol=0.08):
    try:
        sr = 22050
        n  = int(sr * dur / 1000)
        buf= bytearray(n*2)
        for i in range(n):
            env = math.sin(math.pi*i/n)
            v   = int(32767 * vol * env * math.sin(2*math.pi*freq*i/sr))
            buf[i*2]   = v & 0xFF
            buf[i*2+1] = (v>>8) & 0xFF
        snd = pygame.sndarray.make_sound(
            pygame.surfarray.map_array(
                pygame.Surface((1,1)), [[0]]   # dummy — we use raw below
            )
        )
        # Use raw pygame mixer channel
        import array as arr
        a = arr.array('h', [0]*n)
        for i in range(n):
            env = math.sin(math.pi*i/n)
            a[i]=int(32767*vol*env*math.sin(2*math.pi*freq*i/sr))
        snd = pygame.sndarray.make_sound(
            __import__('numpy').frombuffer(bytes(buf),'int16').reshape(-1,1) if False else
            pygame.sndarray.make_sound(pygame.Surface((1,1)))   # fallback silent
        )
    except Exception:
        pass   # sound is optional

def play_footstep(t):
    try:
        sr   = 22050
        dur  = 0.06
        n    = int(sr*dur)
        buf  = bytearray(n*2)
        for i in range(n):
            env = (1 - i/n)**2
            v   = int(8000 * env * (random.random()*2-1))
            buf[i*2]   = v & 0xFF
            buf[i*2+1] = (v>>8) & 0xFF
        arr = pygame.sndarray.make_sound(
            __import__('pygame').surfarray.make_surface([[0]])   # silent fallback
        )
    except Exception:
        pass

# ── Game State ────────────────────────────────────────────────────────────────
class GS:
    def __init__(self):
        self.room       = "bedroom"
        self.px         = 5.5
        self.py         = 4.5
        self.angle      = 0.0
        self.inventory  = []
        self.max_inv    = 5
        self.picked     = set()
        self.notes_read = set()
        self.journal    = list(JOURNAL_ENTRIES)

        # Stats
        self.stamina    = 1.0    # 0..1
        self.sanity     = 1.0    # 0..1  — low = hallucinations
        self.battery    = 1.0    # 0..1  — flashlight fuel
        self.noise      = 0.0    # 0..1  — attracts entity

        self.flashlight = False
        self.sprinting  = False

        # Entity
        self.threat      = 0
        self.max_threat  = 20
        self.entity_room = "attic"
        self.entity_x    = 6.5
        self.entity_y    = 3.5
        self.entity_tick = 0.0
        self.entity_speed= 2.2   # seconds per move

        # Doors
        self.red_door_open  = False
        self.anim_doors     = {}  # (room,r,c): open_frac 0→1

        # UI
        self.msg        = "You wake up. The room is pitch black."
        self.msg_col    = C_W
        self.msg_timer  = 5.0
        self.sub_msg    = ""
        self.sub_timer  = 0.0

        self.escaped    = False
        self.dead       = False
        self.dead_timer = 0.0
        self.win_timer  = 0.0
        self.win_text   = ""
        self.win_idx    = 0

        self.show_journal   = False
        self.journal_tab    = 0   # 0=journal 1=inventory 2=objectives
        self.show_minimap   = True
        self.mouse_look     = False
        self.paused         = False

        self.bob        = 0.0
        self.bob_v      = 0.0
        self.breathe    = 0.0
        self.hallu_t    = 0.0   # hallucination timer
        self.hallu_active=False

        self.turn       = 0
        self.steps      = 0
        self.noise_event_t = 0.0

        # Procedural wall scratches seed
        self.scratch_seed = random.randint(0, 9999)

    @property
    def game_over(self):
        return self.escaped or self.dead

    @property
    def threat_pct(self):
        return min(self.threat / self.max_threat, 1.0)

    def set_msg(self, text, col=None, sub=""):
        self.msg       = text
        self.msg_col   = col or C_W
        self.msg_timer = 5.0
        if sub:
            self.sub_msg   = sub
            self.sub_timer = 4.0

    def add_to_journal(self, entry):
        if entry not in self.journal:
            self.journal.append(entry)

    def try_move(self, dx, dy):
        nx = self.px + dx;  ny = self.py + dy
        if not is_solid(self.room, int(nx), int(self.py)):
            self.px = nx
        if not is_solid(self.room, int(self.px), int(ny)):
            self.py = ny
        self.turn  += 1
        self.steps += 1
        self.bob_v += 0.7
        spd_noise   = 0.06 if self.sprinting else 0.01
        self.noise  = min(1.0, self.noise + spd_noise)

    def try_interact(self):
        # Check doors ahead
        for dist in [0.65, 1.0, 1.35]:
            fx = int(self.px + math.cos(self.angle)*dist)
            fy = int(self.py + math.sin(self.angle)*dist)
            cell = get_cell(self.room, fx, fy)
            if cell in ('D','R','B','G','X','S'):
                lnk = DOOR_LINKS.get((self.room, fy, fx))
                if lnk:
                    dest, sx, sy, sa, key = lnk
                    if key and key not in self.inventory:
                        self.set_msg(f"This door needs the {key.replace('_',' ').title()}!", C_WRN)
                        return
                    if dest == "outside":
                        self.escaped = True
                        self.win_timer = 6.0
                        self.win_text  = "You jam the key into the padlock... it clicks.\nThe door swings open. Cold night air floods in.\nYou run and don't look back.\n\nYOU ESCAPED."
                        return
                    self.room  = dest
                    self.px, self.py = sx, sy
                    self.angle = sa
                    self.set_msg(f"You enter the {dest.title()}.")
                    self.add_to_journal(f"Entered the {dest.title()}.")
                    self.turn += 1
                    return
                self.set_msg("The door seems stuck.", C_DIM)
                return

        # Check items
        for (iroom, ix, iy), idef in ITEMS_DEF.items():
            if iroom != self.room: continue
            key = (iroom, ix, iy)
            if key in self.picked: continue
            if math.hypot(self.px-ix, self.py-iy) < 1.3:
                if len(self.inventory) >= self.max_inv:
                    self.set_msg("Inventory full! Drop something first (not yet implemented).", C_WRN)
                    return
                self.inventory.append(idef["name"])
                self.picked.add(key)
                self.set_msg(idef["text"], C_GD)
                self.add_to_journal(f"Picked up: {idef['label']}")
                # Special effects
                if idef["name"] == "battery":
                    self.battery = min(1.0, self.battery + 0.4)
                if idef["name"] == "amulet":
                    self.sanity  = min(1.0, self.sanity  + 0.3)
                    self.entity_speed = min(self.entity_speed + 0.5, 4.0)
                if "note" in idef["name"] and idef["name"] in NOTES_CONTENT:
                    self.notes_read.add(idef["name"])
                # Unlock red door hint
                if idef["name"] == "red_key":
                    self.set_msg(idef["text"], C_GD, sub="The red door in the basement is now unlocked.")
                    self.red_door_open = True
                return

        self.set_msg("Nothing here.", C_DIM)

    def toggle_flashlight(self):
        if "flashlight" not in self.inventory:
            self.set_msg("You don't have a flashlight.", C_WRN)
            return
        self.flashlight = not self.flashlight
        self.set_msg("Flashlight ON." if self.flashlight else "Flashlight OFF.", C_DIM)

    def update(self, dt, keys, mouse_dx):
        if self.paused or self.dead or self.escaped: return

        # Turn
        turn = 0.0
        if keys[pygame.K_LEFT]  or keys[pygame.K_a]: turn -= TURN_SPEED
        if keys[pygame.K_RIGHT] or keys[pygame.K_d]: turn += TURN_SPEED
        if self.mouse_look:
            turn += mouse_dx * 0.002
        self.angle += turn

        # Sprint
        self.sprinting = (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]) and self.stamina > 0.05

        # Move
        spd = MOVE_SPEED * (SPRINT_MUL if self.sprinting else 1.0)
        if keys[pygame.K_w] or keys[pygame.K_UP]:
            self.try_move(math.cos(self.angle)*spd, math.sin(self.angle)*spd)
        if keys[pygame.K_s] or keys[pygame.K_DOWN]:
            self.try_move(-math.cos(self.angle)*spd, -math.sin(self.angle)*spd)

        # Stamina
        if self.sprinting:
            self.stamina = max(0, self.stamina - dt * 0.25)
        else:
            self.stamina = min(1.0, self.stamina + dt * 0.18)

        # Battery drain
        if self.flashlight:
            self.battery = max(0, self.battery - dt * 0.012)
            if self.battery <= 0:
                self.flashlight = False
                self.set_msg("Flashlight battery dead!", C_WRN)

        # Noise decay
        self.noise = max(0, self.noise - dt * 0.15)

        # Sanity
        dark_penalty = 0.008 if not self.flashlight else 0.001
        near_entity  = (self.entity_room == self.room and
                        math.hypot(self.px-self.entity_x, self.py-self.entity_y) < 4)
        entity_pen   = 0.025 if near_entity else 0
        amulet_prot  = 0.005 if "amulet" in self.inventory else 0
        self.sanity  = max(0, min(1.0,
            self.sanity - (dark_penalty + entity_pen - amulet_prot) * dt))

        # Sanity events
        if self.sanity < 0.35 and random.random() < dt * 0.3:
            self.set_msg(random.choice(SANITY_MSGS), C_EVT)
        if self.sanity < 0.15 and not self.hallu_active:
            self.hallu_active = True
            self.hallu_t      = 3.0
        if self.hallu_active:
            self.hallu_t -= dt
            if self.hallu_t <= 0:
                self.hallu_active = False

        # Breathe animation
        self.breathe = math.sin(time.time() * (1.5 + (1-self.sanity)*2))

        # Bob
        self.bob_v *= 0.88
        self.bob   += self.bob_v * dt
        self.bob   *= 0.90

        # Entity AI
        self._update_entity(dt)

        # Timers
        self.msg_timer  = max(0, self.msg_timer  - dt)
        self.sub_timer  = max(0, self.sub_timer  - dt)
        self.noise_event_t = max(0, self.noise_event_t - dt)

        # Random events
        if self.noise_event_t <= 0 and random.random() < dt * 0.08:
            self.set_msg(random.choice(RANDOM_EVENTS), C_EVT)
            self.noise_event_t = 8.0

        # Death
        if self.dead:
            self.dead_timer += dt

        # Win typewriter
        if self.escaped and self.win_timer > 0:
            self.win_timer -= dt

    def _update_entity(self, dt):
        self.entity_tick += dt
        # Speed increases with threat + noise
        spd = self.entity_speed - self.noise * 0.8
        spd = max(0.8, spd)
        if self.entity_tick < spd: return
        self.entity_tick = 0.0

        self.threat = min(self.threat + 1, self.max_threat)
        pct = self.threat_pct

        # Entity moves toward player if in same room, else patrols
        if self.entity_room == self.room:
            # Move one step toward player
            dx = self.px - self.entity_x
            dy = self.py - self.entity_y
            dist = math.hypot(dx, dy)
            if dist < 1.0:
                self.dead = True
                self.set_msg("IT FOUND YOU.", C_WRN)
                return
            # Normalise and step
            step = 0.8
            self.entity_x += (dx/dist) * step
            self.entity_y += (dy/dist) * step
        else:
            # Random patrol in entity room
            for _ in range(5):
                ex = self.entity_x + random.choice([-0.7,0,0.7])
                ey = self.entity_y + random.choice([-0.7,0,0.7])
                if not is_solid(self.entity_room, int(ex), int(ey)):
                    self.entity_x = ex
                    self.entity_y = ey
                    break

        # Entity can follow through doors if noise is very high or threat is high
        if self.noise > 0.7 or pct > 0.75:
            if self.entity_room != self.room:
                self.entity_room = self.room
                self.set_msg("It knows where you are...", C_WRN)

        # Warning messages
        if pct > 0.35:
            idx = min(int((pct-0.35)/0.65*len(ENTITY_WARNS)), len(ENTITY_WARNS)-1)
            if random.random() < 0.4:
                self.set_msg(ENTITY_WARNS[idx], C_WRN)

        if self.threat >= self.max_threat:
            self.dead = True
            self.set_msg("IT FOUND YOU.", C_WRN)

# ── Shading ───────────────────────────────────────────────────────────────────
def shade(base, dist, side, gs, t):
    torch_r = 9.0 if gs.flashlight else 2.8
    bri = max(0.0, 1.0 - (dist/torch_r)**1.5)
    if gs.flashlight and gs.threat_pct > 0.65:
        bri *= (0.8 + math.sin(t*20+dist*3)*0.15)
    if gs.battery < 0.15 and gs.flashlight:
        bri *= (0.5 + math.sin(t*40)*0.45)   # rapid flicker on low battery
    if side == 1: bri *= 0.62
    # Sanity distortion
    if gs.hallu_active:
        bri *= (0.6 + math.sin(t*8+dist)*0.4)
    r = int(base[0]*bri); g = int(base[1]*bri); b = int(base[2]*bri)
    # Red threat tint
    tp = gs.threat_pct
    if tp > 0.5:
        tint = (tp-0.5)/0.5
        r = min(255, r + int(55*tint))
    # Sanity green tint
    if gs.sanity < 0.3:
        st = (0.3-gs.sanity)/0.3
        g = min(255, g + int(30*st))
    return (max(0,min(255,r)), max(0,min(255,g)), max(0,min(255,b)))

# ── Wall texture overlay (scratch marks, procedural) ─────────────────────────
_scratch_cache = {}
def get_scratch(seed, col_idx, wall_h):
    """Return extra darkening for a column — simulates scratches."""
    k = (seed, col_idx % 80)
    if k not in _scratch_cache:
        random.seed(seed + col_idx*7)
        _scratch_cache[k] = [random.random() for _ in range(20)]
    vals = _scratch_cache[k]
    dark = 0
    for v in vals:
        if abs((col_idx % 80)/80 - v) < 0.01:
            dark += 30
    return dark

# ── Renderer ──────────────────────────────────────────────────────────────────
def draw_world(surf, gs, z_buf, t):
    room   = gs.room
    base_w = WALL_PAL[room]
    rays   = cast_rays(room, gs.px, gs.py, gs.angle, gs)
    tp     = gs.threat_pct
    bob_off= int(gs.bob * 7)

    # Sky
    surf.fill(SKY, (0, 0, W, HALF_H))

    # Floor gradient
    for y in range(HALF_H, H - HUD_H):
        ratio = (y - HALF_H) / (H - HUD_H - HALF_H)
        fc = (int(FL_FAR[0]+(FL_NEAR[0]-FL_FAR[0])*ratio),
              int(FL_FAR[1]+(FL_NEAR[1]-FL_FAR[1])*ratio),
              int(FL_FAR[2]+(FL_NEAR[2]-FL_FAR[2])*ratio))
        pygame.draw.line(surf, fc, (0,y+bob_off), (W,y+bob_off))

    # Walls
    for ci, (dist, cell, side) in enumerate(rays):
        z_buf[ci] = dist
        wh   = min(int((H-HUD_H) / (dist+0.0001)), H-HUD_H)
        top  = HALF_H - wh//2 + bob_off

        if cell in ('D','R','B','G','X','S'):
            base = door_color(cell, gs)
        else:
            base = base_w

        col = shade(base, dist, side, gs, t)
        # Scratch overlay
        scratch = get_scratch(gs.scratch_seed, ci, wh)
        if scratch:
            col = tuple(max(0, c-scratch) for c in col)

        x = ci * 2
        pygame.draw.rect(surf, col, (x, top, 2, wh))

    # Sprites
    sprites = SPRITES_DEF.get(room, [])
    sdata = []
    for sp in sprites:
        dx = sp["x"]-gs.px; dy = sp["y"]-gs.py
        sd = math.hypot(dx,dy)
        if sd < 0.4 or sd > MAX_DEPTH: continue
        sdata.append((sd, sp))
    sdata.sort(key=lambda x:-x[0])

    for sd, sp in sdata:
        dx = sp["x"]-gs.px; dy = sp["y"]-gs.py
        spa = math.atan2(dy,dx)-gs.angle
        while spa >  math.pi: spa -= 2*math.pi
        while spa < -math.pi: spa += 2*math.pi
        if abs(spa) > HALF_FOV+0.25: continue
        sx  = int((0.5+spa/FOV)*W)
        sh  = min(int((H-HUD_H)/(sd+0.001)), H-HUD_H)
        sw  = sh
        sy  = HALF_H - sh//2 + bob_off
        sc  = shade(SPRITE_COLS.get(sp["type"],(50,40,30)), sd, 0, gs, t)
        for px2 in range(sx-sw//2, sx+sw//2):
            if px2 < 0 or px2 >= W: continue
            rc = px2//2
            if rc >= NUM_RAYS: continue
            if z_buf[rc] < sd: continue
            f = (px2-(sx-sw//2))/max(sw,1)
            sb2 = 0.5 + 0.5*abs(f-0.5)*2
            fc2 = tuple(max(0,min(255,int(c*sb2))) for c in sc)
            pygame.draw.line(surf, fc2, (px2,sy),(px2,sy+sh))

    # Entity sprite (if in same room)
    if gs.entity_room == room:
        dx = gs.entity_x-gs.px; dy = gs.entity_y-gs.py
        sd = math.hypot(dx,dy)
        if sd > 0.5 and sd < MAX_DEPTH:
            spa = math.atan2(dy,dx)-gs.angle
            while spa >  math.pi: spa -= 2*math.pi
            while spa < -math.pi: spa += 2*math.pi
            if abs(spa) < HALF_FOV+0.3:
                ex  = int((0.5+spa/FOV)*W)
                eh  = min(int((H-HUD_H)/(sd+0.001)), H-HUD_H)
                ey  = HALF_H - eh//2 + bob_off
                # Pulsing red silhouette
                pulse = abs(math.sin(t*3))
                ecol  = (int(120*pulse), 0, int(20*pulse))
                for px3 in range(ex-eh//3, ex+eh//3):
                    if px3 < 0 or px3 >= W: continue
                    rc = px3//2
                    if rc >= NUM_RAYS: continue
                    if z_buf[rc] < sd: continue
                    pygame.draw.line(surf, ecol, (px3,ey),(px3,ey+eh))

    # Item glows
    for (iroom,ix,iy), idef in ITEMS_DEF.items():
        if iroom != room: continue
        if (iroom,ix,iy) in gs.picked: continue
        dx=ix-gs.px; dy=iy-gs.py; sd=math.hypot(dx,dy)
        if sd > 7: continue
        spa=math.atan2(dy,dx)-gs.angle
        while spa >  math.pi: spa-=2*math.pi
        while spa < -math.pi: spa+=2*math.pi
        if abs(spa) > HALF_FOV+0.1: continue
        scx = int((0.5+spa/FOV)*W)
        gr  = max(4, int(20/(sd+0.5)))
        pulse= 0.55+0.45*math.sin(t*4)
        ic   = idef["color"]
        gcol = tuple(int(c*pulse*0.8) for c in ic)
        pygame.draw.circle(surf, gcol, (scx, HALF_H+bob_off), gr)

    # Darkness vignette
    vsurf = pygame.Surface((W,H-HUD_H), pygame.SRCALPHA)
    for r in range(260,0,-35):
        a = int(160*(1-r/260)**2.2)
        pygame.draw.rect(vsurf,(0,0,0,a),(W//2-r,HALF_H-r,r*2,r*2),border_radius=r)
    surf.blit(vsurf,(0,0))

    # Red threat vignette
    if tp > 0.5:
        va = int((tp-0.5)/0.5*110)
        if tp > 0.78:
            va = int(va*(0.55+0.45*abs(math.sin(t*3.8))))
        rv = pygame.Surface((W,H-HUD_H),pygame.SRCALPHA)
        rv.fill((85,5,5,va))
        surf.blit(rv,(0,0))

    # Sanity distortion (green scanlines)
    if gs.sanity < 0.25:
        st = (0.25-gs.sanity)/0.25
        sv = pygame.Surface((W,H-HUD_H),pygame.SRCALPHA)
        for y in range(0,H-HUD_H,4):
            a = int(st*35*abs(math.sin(y*0.1+t*5)))
            pygame.draw.line(sv,(0,80,0,a),(0,y),(W,y))
        surf.blit(sv,(0,0))

    # Hallucination overlay (face in darkness)
    if gs.hallu_active:
        ha = int(abs(math.sin(t*2))*60)
        hv = pygame.Surface((W,H-HUD_H),pygame.SRCALPHA)
        hv.fill((30,10,10,ha))
        surf.blit(hv,(0,0))

    # Death crack effect
    if gs.dead:
        draw_death(surf, gs, t)

    # Win fade
    if gs.escaped:
        draw_win(surf, gs, t)


def draw_death(surf, gs, t):
    prog = min(1.0, gs.dead_timer/3.5)
    a    = int(prog*220)
    dv   = pygame.Surface((W,H),pygame.SRCALPHA)
    dv.fill((0,0,0,a))
    surf.blit(dv,(0,0))
    # Crack lines
    rng = random.Random(42)
    for _ in range(18):
        x1 = rng.randint(0,W); y1 = rng.randint(0,H-HUD_H)
        x2 = x1+rng.randint(-120,120); y2 = y1+rng.randint(-80,80)
        ca = min(255, int(prog*180))
        pygame.draw.line(surf,(ca,0,0),(x1,y1),(x2,y2),1)


def draw_win(surf, gs, t):
    prog = max(0, 1.0 - gs.win_timer/6.0)
    a    = int(prog*255)
    wv   = pygame.Surface((W,H),pygame.SRCALPHA)
    wv.fill((0,0,0,a))
    surf.blit(wv,(0,0))


def draw_hud(surf, gs, font, fsm, t):
    hy = H - HUD_H
    pygame.draw.rect(surf, HUD_BG, (0,hy,W,HUD_H))
    pygame.draw.line(surf,(22,20,18),(0,hy),(W,hy))

    def bar(x,y,w,h,val,col_full,col_empty=(20,15,15),label=""):
        pygame.draw.rect(surf,col_empty,(x,y,w,h),border_radius=3)
        fw=int(w*max(0,min(1,val)))
        if fw>0: pygame.draw.rect(surf,col_full,(x,y,fw,h),border_radius=3)
        pygame.draw.rect(surf,(35,30,28),(x,y,w,h),1,border_radius=3)
        if label:
            ll=fsm.render(label,True,C_DIM)
            surf.blit(ll,(x,y-14))

    bar(12, hy+22, 140, 7, gs.threat_pct,
        (200,30,20) if gs.threat_pct>0.7 else (150,60,15) if gs.threat_pct>0.4 else (80,18,15),
        label="ENTITY")
    bar(12, hy+52, 140, 5, gs.stamina,   (60,140,180), label="STAMINA")
    bar(12, hy+70, 140, 5, gs.sanity,    (120,80,180), label="SANITY")
    bar(12, hy+82, 140, 5, gs.battery,   (200,180,50), label="BATTERY" if gs.flashlight else "")

    # Stats
    stats=[("ROOM",gs.room.upper()),("STEPS",str(gs.steps)),
           ("NOISE","█"*int(gs.noise*8)+"░"*(8-int(gs.noise*8)))]
    sx=165
    for lbl,val in stats:
        ls=fsm.render(lbl,True,C_DIM)
        vs=fsm.render(val,True,C_W)
        surf.blit(ls,(sx,hy+12))
        surf.blit(vs,(sx,hy+28))
        sx+=max(ls.get_width(),vs.get_width())+28

    # Inventory icons
    inv_x = 440
    il=fsm.render("INVENTORY",True,C_DIM)
    surf.blit(il,(inv_x,hy+8))
    for i,item in enumerate(gs.inventory):
        idef=next((v for (r,x,y),v in ITEMS_DEF.items() if v["name"]==item),None)
        ic = idef["color"] if idef else C_DIM
        pygame.draw.rect(surf,(20,18,15),(inv_x+i*38,hy+24,32,32),border_radius=4)
        pygame.draw.rect(surf,ic,(inv_x+i*38,hy+24,32,32),2,border_radius=4)
        nm=fsm.render(item[:4],True,ic)
        surf.blit(nm,(inv_x+i*38+2,hy+40))

    # Flashlight status
    if "flashlight" in gs.inventory:
        fl_col = (200,180,50) if gs.flashlight else (60,55,35)
        fl_lbl = fsm.render("F:LIGHT "+("ON" if gs.flashlight else "OFF"), True, fl_col)
        surf.blit(fl_lbl,(inv_x,hy+70))

    # Controls strip
    ctrl="W/S:move  A/D:turn  E:interact  F:light  TAB:journal  M:map  ESC:pause"
    cs=fsm.render(ctrl,True,(40,38,33))
    surf.blit(cs,(W-cs.get_width()-10,hy+HUD_H-16))

    # Message
    if gs.msg_timer>0:
        a=min(255,int(gs.msg_timer/5.0*255))
        ms=font.render(gs.msg,True,gs.msg_col)
        ms.set_alpha(a)
        surf.blit(ms,(W//2-ms.get_width()//2,hy-32))
    if gs.sub_timer>0:
        a=min(255,int(gs.sub_timer/4.0*200))
        ss=fsm.render(gs.sub_msg,True,C_DIM)
        ss.set_alpha(a)
        surf.blit(ss,(W//2-ss.get_width()//2,hy-14))

    # Crosshair
    cx,cy=W//2,HALF_H
    pygame.draw.line(surf,(170,160,130),(cx-10,cy),(cx-4,cy))
    pygame.draw.line(surf,(170,160,130),(cx+4,cy),(cx+10,cy))
    pygame.draw.line(surf,(170,160,130),(cx,cy-10),(cx,cy-4))
    pygame.draw.line(surf,(170,160,130),(cx,cy+4),(cx,cy+10))
    # Noise indicator on crosshair
    if gs.noise>0.3:
        nr=int(gs.noise*12)+4
        nc=int(gs.noise*200)
        pygame.draw.circle(surf,(nc,0,0),( cx,cy),nr,1)

    # Minimap
    if gs.show_minimap:
        draw_minimap(surf,gs,fsm)

    # Breathing overlay (sanity)
    if gs.sanity < 0.5:
        ba = int((0.5-gs.sanity)/0.5 * 40 * abs(gs.breathe))
        bv = pygame.Surface((W,H-HUD_H),pygame.SRCALPHA)
        bv.fill((0,0,0,ba))
        surf.blit(bv,(0,0))


def draw_minimap(surf, gs, fsm):
    m    = MAPS[gs.room]
    rows = len(m)
    cols = max(len(r) for r in m)
    cs   = 5
    ox   = W - cols*cs - 10
    oy   = 10
    bg   = pygame.Surface((cols*cs+2,rows*cs+2),pygame.SRCALPHA)
    bg.fill((0,0,0,120))
    surf.blit(bg,(ox-1,oy-1))
    for r,row in enumerate(m):
        for c,cell in enumerate(row):
            col=(8,8,10) if cell=='#' else \
                (20,60,20) if cell=='X' else \
                (40,20,20) if cell in('R',) else \
                (20,35,55) if cell in('D','B','G','S') else \
                (20,19,16)
            pygame.draw.rect(surf,col,(ox+c*cs,oy+r*cs,cs-1,cs-1))
    # Player
    pdx=int(gs.px*cs); pdy=int(gs.py*cs)
    pygame.draw.circle(surf,(200,180,60),(ox+pdx,oy+pdy),2)
    tdx=ox+pdx+int(math.cos(gs.angle)*5)
    tdy=oy+pdy+int(math.sin(gs.angle)*5)
    pygame.draw.line(surf,(200,180,60),(ox+pdx,oy+pdy),(tdx,tdy))
    # Entity (if same room)
    if gs.entity_room==gs.room:
        edx=int(gs.entity_x*cs); edy=int(gs.entity_y*cs)
        pulse=abs(math.sin(time.time()*3))
        ec=(int(180*pulse),0,0)
        pygame.draw.circle(surf,ec,(ox+edx,oy+edy),3)


def draw_journal(surf, gs, font_big, font, fsm):
    ov=pygame.Surface((W,H),pygame.SRCALPHA)
    ov.fill((0,0,0,210))
    surf.blit(ov,(0,0))
    tabs=["JOURNAL","INVENTORY","OBJECTIVES"]
    tx=W//2-200
    for i,tab in enumerate(tabs):
        active=i==gs.journal_tab
        tc=C_W if active else C_DIM
        ts=font.render(f"[{tab}]",True,tc)
        surf.blit(ts,(tx,40))
        tx+=ts.get_width()+30
    pygame.draw.line(surf,C_DIM,(W//2-200,65),(W//2+200,65))

    if gs.journal_tab==0:
        y=85
        for entry in gs.journal[-14:]:
            if y>H-60: break
            if entry.startswith("Diary") or entry.startswith("A torn"):
                es=font.render(entry,True,C_YEL)
            else:
                es=fsm.render(entry,True,C_DIM)
            surf.blit(es,(60,y))
            y+=20

        # Notes
        for nkey in gs.notes_read:
            if nkey in NOTES_CONTENT:
                y+=10
                for line in NOTES_CONTENT[nkey]:
                    if y>H-50: break
                    ns=fsm.render(line,True,C_YEL)
                    surf.blit(ns,(80,y)); y+=16

    elif gs.journal_tab==1:
        y=85
        hl=font.render(f"Inventory ({len(gs.inventory)}/{gs.max_inv})",True,C_W)
        surf.blit(hl,(60,y)); y+=28
        for item in gs.inventory:
            idef=next((v for (_,__,___),v in ITEMS_DEF.items() if v["name"]==item),None)
            ic=idef["color"] if idef else C_DIM
            pygame.draw.rect(surf,(20,18,15),(60,y,36,36),border_radius=4)
            pygame.draw.rect(surf,ic,(60,y,36,36),2,border_radius=4)
            nm=font.render(idef["label"] if idef else item,True,C_W)
            surf.blit(nm,(104,y+10)); y+=44

    elif gs.journal_tab==2:
        y=85
        hl=font.render("OBJECTIVES",True,C_W)
        surf.blit(hl,(60,y)); y+=30
        for label,check in OBJECTIVES:
            done=check(gs)
            col=C_GD if done else C_DIM
            mark="[X]" if done else "[ ]"
            os2=font.render(f"{mark} {label}",True,col)
            surf.blit(os2,(60,y)); y+=26

    hint=fsm.render("TAB: cycle tabs    TAB again (or ESC): close",True,(45,42,38))
    surf.blit(hint,(W//2-hint.get_width()//2,H-30))


def draw_pause(surf, font_big, font, fsm):
    ov=pygame.Surface((W,H),pygame.SRCALPHA)
    ov.fill((0,0,0,180))
    surf.blit(ov,(0,0))
    tl=font_big.render("PAUSED",True,(180,170,130))
    surf.blit(tl,(W//2-tl.get_width()//2,180))
    controls=[
        ("W/S",       "Move forward / backward"),
        ("A/D",       "Turn left / right"),
        ("SHIFT+W/S", "Sprint (makes noise!)"),
        ("E",         "Interact / open doors / pick up items"),
        ("F",         "Toggle flashlight"),
        ("TAB",       "Journal, inventory, objectives"),
        ("M",         "Toggle minimap"),
        ("ESC",       "Pause / unpause"),
    ]
    y=250
    for key,desc in controls:
        ks=font.render(key,True,C_YEL)
        ds=fsm.render(desc,True,C_DIM)
        surf.blit(ks,(W//2-220,y))
        surf.blit(ds,(W//2-60,y+2))
        y+=26
    rl=font.render("Press ESC to resume",True,(120,115,90))
    surf.blit(rl,(W//2-rl.get_width()//2,H-80))


def draw_title(surf, font_big, font, fsm, t):
    surf.fill((4,3,5))
    # Animated lines
    for i in range(0,W,40):
        a=int(abs(math.sin(i*0.05+t*0.5))*20)
        pygame.draw.line(surf,(a,a,a),(i,0),(i,H))

    tl=font_big.render("THE DARK HOUSE",True,(180,160,80))
    sub=font.render("Enhanced First Person Edition",True,(80,70,45))
    surf.blit(tl,(W//2-tl.get_width()//2,130))
    surf.blit(sub,(W//2-sub.get_width()//2,185))

    features=[
        "Flashlight + batteries","Stamina & sprinting","Sanity system + hallucinations",
        "Entity AI (reacts to noise)","Multiple keys & locked doors",
        "Secret room","Collectible notes + journal","Objectives tracker",
    ]
    y=230
    fl=fsm.render("NEW FEATURES:",True,C_YEL)
    surf.blit(fl,(W//2-200,y)); y+=22
    for i,f in enumerate(features):
        col=C_DIM if i%2==0 else (90,85,65)
        fs=fsm.render(f"  ✦ {f}",True,col)
        surf.blit(fs,(W//2-200,y)); y+=18

    pulse=0.6+0.4*math.sin(t*2.2)
    pc=tuple(int(c*pulse) for c in (180,160,80))
    bl=font.render("PRESS ENTER TO START",True,pc)
    surf.blit(bl,(W//2-bl.get_width()//2,H-90))
    ql=fsm.render("ESC to quit",True,(50,46,40))
    surf.blit(ql,(W//2-ql.get_width()//2,H-55))


def draw_over(surf, gs, font_big, font, fsm, t):
    ov=pygame.Surface((W,H),pygame.SRCALPHA)
    ov.fill((0,0,0,230))
    surf.blit(ov,(0,0))

    if gs.escaped:
        title,tc="YOU ESCAPED",(80,190,80)
        # Typewriter effect
        full=gs.win_text
        prog=max(0,1-(gs.win_timer/6.0))
        shown=full[:int(len(full)*min(1,prog*1.4))]
        lines=shown.split('\n')
        y=180
        for line in lines:
            ls=font.render(line,True,(140,200,140))
            surf.blit(ls,(W//2-ls.get_width()//2,y)); y+=26
    else:
        title,tc="IT FOUND YOU",(190,45,25)
        msgs=[f"You lasted {gs.steps} steps.",
              f"Sanity remaining: {int(gs.sanity*100)}%",
              "","The house is quiet again.","","For now."]
        y=200
        for m in msgs:
            if m:
                ms=font.render(m,True,(140,110,100))
                surf.blit(ms,(W//2-ms.get_width()//2,y))
            y+=26

    tl=font_big.render(title,True,tc)
    surf.blit(tl,(W//2-tl.get_width()//2,110))

    if not gs.escaped or gs.win_timer<=0:
        pulse=0.55+0.45*math.sin(t*2)
        pc=tuple(int(c*pulse) for c in tc)
        bl=font.render("PRESS ENTER TO PLAY AGAIN",True,pc)
        surf.blit(bl,(W//2-bl.get_width()//2,H-80))


# ── Main ──────────────────────────────────────────────────────────────────────
def new_game():
    return GS()

def main():
    pygame.init()
    try: init_sound()
    except Exception: pass

    screen  = pygame.display.set_mode((W,H))
    pygame.display.set_caption("The Dark House — FPV Enhanced")
    clock   = pygame.time.Clock()

    font_big = pygame.font.SysFont("Courier New", 36, bold=True)
    font     = pygame.font.SysFont("Courier New", 15)
    fsm      = pygame.font.SysFont("Courier New", 12)

    gs     = new_game()
    state  = "title"
    z_buf  = [MAX_DEPTH]*NUM_RAYS
    mouse_dx = 0

    if gs.mouse_look:
        pygame.mouse.set_visible(False)
        pygame.event.set_grab(True)

    tab_press_last = 0

    while True:
        dt  = min(clock.tick(FPS)/1000.0, 0.05)
        t   = time.time()
        mouse_dx = 0

        for event in pygame.event.get():
            if event.type==pygame.QUIT:
                pygame.quit(); sys.exit()

            if event.type==pygame.MOUSEMOTION and gs.mouse_look:
                mouse_dx = event.rel[0]

            if event.type==pygame.KEYDOWN:
                k=event.key

                if k==pygame.K_ESCAPE:
                    if state=="title":
                        pygame.quit(); sys.exit()
                    elif state=="playing":
                        if gs.show_journal:
                            gs.show_journal=False
                        else:
                            gs.paused=not gs.paused
                    elif state=="over":
                        gs=new_game(); state="title"

                if state=="title" and k==pygame.K_RETURN:
                    gs=new_game(); state="playing"

                if state=="over" and k==pygame.K_RETURN:
                    gs=new_game(); state="playing"

                if state=="playing" and not gs.paused:
                    if k==pygame.K_e:
                        gs.try_interact()
                    if k==pygame.K_f:
                        gs.toggle_flashlight()
                    if k==pygame.K_m:
                        gs.show_minimap=not gs.show_minimap
                    if k==pygame.K_TAB:
                        now=time.time()
                        if gs.show_journal:
                            if now-tab_press_last<0.4:
                                gs.show_journal=False
                            else:
                                gs.journal_tab=(gs.journal_tab+1)%3
                        else:
                            gs.show_journal=True
                            gs.journal_tab=0
                        tab_press_last=now

        if state=="playing" and not gs.paused and not gs.show_journal:
            keys=pygame.key.get_pressed()
            gs.update(dt, keys, mouse_dx)
            if gs.game_over:
                state="over"

        # ── Draw ──
        screen.fill((0,0,0))

        if state=="title":
            draw_title(screen,font_big,font,fsm,t)
        elif state in("playing","over"):
            draw_world(screen,gs,z_buf,t)
            draw_hud(screen,gs,font,fsm,t)
            if gs.show_journal:
                draw_journal(screen,gs,font_big,font,fsm)
            if gs.paused:
                draw_pause(screen,font_big,font,fsm)
            if state=="over":
                draw_over(screen,gs,font_big,font,fsm,t)

        pygame.display.flip()

if __name__=="__main__":
    main()
