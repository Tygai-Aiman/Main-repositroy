"""On-screen hook text like "GTA 6 airport 🤯", picked from what's said in the clip."""
import re

# (keywords, hook) - first match wins, checked against clip transcript then stream title.
RULES = [
    (["airport", "runway", "terminal"], "GTA 6 airport 🤯"),
    (["plane", "jet", "airplane"], "Flying in GTA 6 ✈️"),
    (["helicopter", "heli", "chopper"], "GTA 6 helicopter 🚁"),
    (["alligator", "gator", "crocodile"], "GTA 6 alligator 🐊"),
    (["swamp", "everglades"], "GTA 6 swamp 🐊"),
    (["bank", "heist", "vault"], "GTA 6 heist 💰"),
    (["rob", "robbery", "robbing", "register"], "GTA 6 robbery 💰"),
    (["chase", "pursuit", "running from"], "GTA 6 police chase 😳"),
    (["cops", "police", "wanted", "stars"], "GTA 6 cops are INSANE 🚔"),
    (["busted", "arrest", "arrested", "jail"], "Busted in GTA 6 🚓"),
    (["explode", "explosion", "exploded", "blew up", "boom"], "GTA 6 explosion 💥"),
    (["crash", "crashed", "wrecked"], "This GTA 6 crash 💀"),
    (["boat", "jet ski", "jetski", "yacht"], "GTA 6 boat 🚤"),
    (["beach", "ocean", "wave"], "GTA 6 beach 🏖️"),
    (["vice city", "miami", "leonida"], "Vice City in GTA 6 🌴"),
    (["physics", "ragdoll"], "GTA 6 physics 🤯"),
    (["npc", "pedestrian", "people"], "GTA 6 NPCs are crazy 😂"),
    (["graphics", "realistic", "look at this", "so real"], "GTA 6 graphics 🤯"),
    (["funny", "laugh", "lmao", "hilarious"], "GTA 6 is hilarious 😂"),
]
FALLBACKS = ["GTA 6 is INSANE 🤯", "Wait for it... 😳", "Only in GTA 6 💀",
             "This is GTA 6?! 😱", "GTA 6 moment 🔥", "Bro did NOT expect this 😂"]


def _has(text, kw):
    return re.search(r"\b" + re.escape(kw) + r"\b", text) is not None


def pick_hook(transcript, stream_title, used):
    for source in (transcript.lower(), stream_title.lower()):
        for kws, hook in RULES:
            if hook not in used and any(_has(source, k) for k in kws):
                return hook
    for f in FALLBACKS:
        if f not in used:
            return f
    return FALLBACKS[0]
