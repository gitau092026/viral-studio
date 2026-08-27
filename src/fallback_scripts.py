"""Built-in bank of ORIGINAL motivation scripts.

These let the pipeline run with zero API keys, and act as a quality bar for
Gemini-generated scripts. Each is a distinct angle (not a template) to stay on
the right side of YouTube's "repetitious / mass-produced" policy — always add or
edit before publishing so your channel reads as authentic.

Shape: {title, hashtags, beats: [{text, broll_query}]}
  - beat[0]  = the HOOK (must land in ~1 second)
  - beat[-1] = the close / soft CTA
  - broll_query = what to search on Pexels for that line's visuals
"""
from .settings import niche_tag

SCRIPTS = [
    {
        "title": "Discipline Beats Motivation Every Time",
        "hashtags": ["#motivation", "#discipline", "#mindset", "#shorts", "#selfimprovement"],
        "beats": [
            {"text": "Stop waiting to feel motivated.", "broll_query": "man walking alone rain city night"},
            {"text": "Motivation is a feeling. Feelings lie.", "broll_query": "storm clouds dramatic sky"},
            {"text": "Discipline shows up when the feeling is gone.", "broll_query": "athlete training dark gym"},
            {"text": "The work you avoid today becomes the person you resent tomorrow.", "broll_query": "man thinking window sunrise"},
            {"text": "So do it tired. Do it bored. Do it scared.", "broll_query": "runner sunrise determination"},
            {"text": "Because discipline is just love for your future self.", "broll_query": "sunrise over mountains cinematic"},
            {"text": "Start now. Your future is watching.", "broll_query": "person standing mountain peak victory"},
        ],
    },
    {
        "title": "Why 5AM Changes Everything",
        "hashtags": ["#motivation", "#5amclub", "#success", "#shorts", "#discipline"],
        "beats": [
            {"text": "Win the morning, win the day.", "broll_query": "sunrise city skyline aerial"},
            {"text": "While the world sleeps, you get a head start nobody can take.", "broll_query": "empty street dawn quiet"},
            {"text": "Two silent hours before the noise begins.", "broll_query": "coffee steam morning desk"},
            {"text": "No notifications. No excuses. Just you and the work.", "broll_query": "person writing journal morning light"},
            {"text": "That quiet is where champions are built.", "broll_query": "swimmer training early morning pool"},
            {"text": "You don't need more time. You need an earlier start.", "broll_query": "alarm clock sunrise window"},
            {"text": "Set the alarm. Meet the person you could become.", "broll_query": "man sunrise rooftop city"},
        ],
    },
    {
        "title": "Comfort Is Quietly Killing You",
        "hashtags": ["#mindset", "#motivation", "#growth", "#shorts", "#stoicism"],
        "beats": [
            {"text": "Comfort feels safe. It's slowly stealing your life.", "broll_query": "person alone dark room window"},
            {"text": "Nothing grows in a comfort zone. Nothing.", "broll_query": "dry cracked desert ground"},
            {"text": "The body you want, the money you want, the peace you want — all live on the other side of hard.", "broll_query": "climber cliff edge sunset"},
            {"text": "Every time you choose easy, you vote against the person you swore you'd become.", "broll_query": "fork in road forest path"},
            {"text": "Discomfort is not the enemy. It's the price.", "broll_query": "boxer training sweat intense"},
            {"text": "Pay it daily, in small amounts.", "broll_query": "person doing pushups sunrise"},
            {"text": "Get uncomfortable on purpose. That's where you're free.", "broll_query": "surfer big wave ocean"},
        ],
    },
    {
        "title": "Stop Comparing Your Chapter One",
        "hashtags": ["#selfimprovement", "#motivation", "#mentalhealth", "#shorts", "#mindset"],
        "beats": [
            {"text": "You're comparing your behind-the-scenes to their highlight reel.", "broll_query": "person scrolling phone dark"},
            {"text": "That's not honesty. That's self-sabotage.", "broll_query": "shattered glass slow motion"},
            {"text": "Their chapter twenty is not your chapter one.", "broll_query": "open book pages turning"},
            {"text": "Every person you envy started as a beginner who kept going.", "broll_query": "child learning to walk"},
            {"text": "Run your own race. The only rival that matters is who you were yesterday.", "broll_query": "lone runner track sunrise"},
            {"text": "Small progress is still progress.", "broll_query": "plant growing time lapse"},
            {"text": "Eyes on your lane. Keep moving.", "broll_query": "highway road trip open view"},
        ],
    },
    {
        "title": "Consistency Is the Real Superpower",
        "hashtags": ["#discipline", "#motivation", "#habits", "#shorts", "#success"],
        "beats": [
            {"text": "You don't need to be extreme. You need to be consistent.", "broll_query": "waves hitting rock ocean"},
            {"text": "One workout won't change you. Three hundred will.", "broll_query": "gym weights training montage"},
            {"text": "The magic isn't intensity. It's showing up when it's boring.", "broll_query": "person tying running shoes"},
            {"text": "Water carves canyons not by force, but by never stopping.", "broll_query": "canyon river aerial view"},
            {"text": "Small habits, repeated, become a different life.", "broll_query": "calendar checkmarks routine"},
            {"text": "So shrink the goal until you can't say no.", "broll_query": "single step staircase light"},
            {"text": "Then do it again tomorrow. And win.", "broll_query": "sunrise runner victory arms up"},
        ],
    },
    {
        "title": "Failure Is Not the Opposite of Success",
        "hashtags": ["#motivation", "#mindset", "#resilience", "#shorts", "#growth"],
        "beats": [
            {"text": "Failure isn't the opposite of success. It's part of it.", "broll_query": "person falling getting up training"},
            {"text": "Every expert was once a disaster who refused to quit.", "broll_query": "artist painting focused studio"},
            {"text": "You learn nothing from the wins you were supposed to get.", "broll_query": "chess game hands close up"},
            {"text": "The scar is proof you fought. The lesson is the reward.", "broll_query": "climber gripping rock cliff"},
            {"text": "Fall seven times. Stand up eight.", "broll_query": "boxer rising from ground"},
            {"text": "Fail faster. Learn quicker. Grow harder.", "broll_query": "fast city timelapse lights"},
            {"text": "The only real failure is stopping. Don't.", "broll_query": "sunrise mountain summit hiker"},
        ],
    },
    {
        "title": "Silence the Noise, Find Your Focus",
        "hashtags": ["#stoicism", "#focus", "#motivation", "#shorts", "#mindset"],
        "beats": [
            {"text": "Your attention is the most expensive thing you own.", "broll_query": "calm lake still water reflection"},
            {"text": "And you're giving it away for free, all day.", "broll_query": "busy crowd blurred motion"},
            {"text": "Every ping pulls you further from the life you say you want.", "broll_query": "phone notifications glowing screen"},
            {"text": "Protect your focus like your future depends on it — because it does.", "broll_query": "person meditating sunrise silhouette"},
            {"text": "Turn off the noise. Sit with the hard thing.", "broll_query": "quiet forest morning mist"},
            {"text": "Deep work in a distracted world is a superpower.", "broll_query": "person writing focused lamp light"},
            {"text": "Guard your mind. Build in silence.", "broll_query": "starry night sky mountains"},
        ],
    },
    {
        "title": "Nobody Is Coming to Save You",
        "hashtags": ["#motivation", "#discipline", "#selfmade", "#shorts", "#mindset"],
        "beats": [
            {"text": "Here's the hard truth: nobody is coming to save you.", "broll_query": "man standing alone vast landscape"},
            {"text": "No perfect moment. No secret shortcut. No rescue.", "broll_query": "empty desert road horizon"},
            {"text": "And that's the best news you'll ever hear.", "broll_query": "sunrise breaking through clouds"},
            {"text": "Because if it's up to you, then it's actually possible.", "broll_query": "person lifting heavy barbell"},
            {"text": "The hand that lifts you is at the end of your own arm.", "broll_query": "hand reaching toward light"},
            {"text": "Stop waiting for permission. Take responsibility.", "broll_query": "person climbing stairs determined"},
            {"text": "You are the plan. Go build it.", "broll_query": "city skyline sunset construction"},
        ],
    },
]


_EXAMPLE_NICHE_TERMS = ("motivation", "self improvement", "self-improvement", "discipline", "mindset", "stoic")


def is_example_niche(niche: str | None) -> bool:
    """True when the niche is (close to) the built-in motivation example the SCRIPTS bank covers."""
    n = (niche or "").lower()
    return any(term in n for term in _EXAMPLE_NICHE_TERMS)


def generic_script(topic: str | None, niche: str) -> dict:
    """A neutral, on-topic scaffold for any niche when no LLM is available.

    Deliberately generic — a starting point to EDIT, not to publish as-is. Add the
    free Gemini key for scripts genuinely tailored to your niche and topic. This
    exists so the no-key path never emits motivation content for an unrelated niche.
    """
    niche = (niche or "content").strip()
    subject = (topic or niche).strip()
    q = f"cinematic {niche}"
    beats = [
        {"text": f"Here's what most people get wrong about {subject}.", "broll_query": q},
        {"text": "It's not what you were told.", "broll_query": f"{niche} close up detail"},
        {"text": f"The real key to {subject} is simpler than it looks.", "broll_query": f"{niche} hands working"},
        {"text": "It comes down to one thing, done consistently.", "broll_query": f"{niche} daily routine"},
        {"text": "Small steps repeated beat one big push every time.", "broll_query": f"{niche} progress"},
        {"text": "So start today — even if it's messy.", "broll_query": f"{niche} beginner start"},
        {"text": "Save this so you actually follow through.", "broll_query": q},
    ]
    tag = niche_tag(niche)
    hashtags = ([tag] if tag else []) + ["#shorts", "#tips"]
    title = (topic or f"The truth about {niche}").strip()
    return {"title": title[:60], "hashtags": hashtags, "beats": beats}


def fallback_ideas(niche: str | None, count: int) -> list[dict]:
    """Concept seeds for the Ideas panel when no LLM is available."""
    if is_example_niche(niche):
        return [
            {"title": s["title"], "hook": s["beats"][0]["text"],
             "angle": "Built-in original concept", "hashtags": s["hashtags"]}
            for s in SCRIPTS
        ][:count]
    n = (niche or "your niche").strip()
    tag = niche_tag(n)
    hashtags = ([tag] if tag else []) + ["#shorts", "#tips"]
    seeds = [
        ("The biggest myth about {n}", "Everyone believes this about {n} — and it's wrong."),
        ("The {n} mistake beginners make", "If you're new to {n}, avoid this first."),
        ("A tiny {n} habit that compounds", "One small {n} habit changes everything."),
        ("What I wish I knew about {n}", "Nobody told me this when I started {n}."),
        ("Stop overcomplicating {n}", "You're making {n} harder than it needs to be."),
        ("The one {n} rule that matters", "Ignore the noise — {n} comes down to this."),
        ("How to start {n} today", "You could start {n} in the next five minutes."),
        ("{n}: what actually moves the needle", "Most {n} advice is noise. This isn't."),
    ]
    return [
        {"title": t.format(n=n)[:60], "hook": h.format(n=n),
         "angle": "Generic seed — edit it, or add a Gemini key for tailored ideas", "hashtags": hashtags}
        for t, h in seeds[:count]
    ]


def pick(topic: str | None = None, niche: str | None = None):
    """Return an on-topic script for this niche.

    For the built-in motivation example niche, match the curated bank by keyword.
    For any other niche, synthesize a generic on-topic scaffold (never motivation).
    """
    if niche and not is_example_niche(niche):
        return generic_script(topic, niche)
    if not topic:
        return SCRIPTS[0]
    t = topic.lower()
    best, best_score = None, -1
    for s in SCRIPTS:
        hay = (s["title"] + " " + " ".join(b["text"] for b in s["beats"]) + " " + " ".join(s["hashtags"])).lower()
        score = sum(1 for w in t.split() if w in hay)
        if score > best_score:
            best, best_score = s, score
    return best or SCRIPTS[0]
