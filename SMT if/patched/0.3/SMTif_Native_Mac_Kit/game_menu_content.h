// game_menu_content.h -- per-game text for game_menu.cpp: Shin Megami Tensei if...
// (The SMT Recomp launcher writes a file like this for every game it builds.)
#pragma once
#define GM_TITLE "SHIN MEGAMI TENSEI if..."
#define GM_PROVIDER_NAME "SMT if... menu"

// An original player's guide for this English edition (not the 1994/2002 manual).
static const ManualSection kManual[] = {
{"The story so far",
"Karukozaka High School, an ordinary weekday afternoon. A student named Hazama, "
"pushed past breaking point, has used a computer program to call up demons, and "
"in one moment the whole school is torn out of the human world and dropped into "
"the Demon World.\n\n"
"You are one of the students left inside. Hazama now calls himself the Demon "
"Emperor, and the corridors you knew are full of demons. With a classmate at "
"your side and a demon-summoning program on your arm, you have to find a way "
"through the realms that surround the school and bring everyone home."},
{"Starting a new game",
"Press Start on the title screen and choose to begin a new game.\n\n"
"Nova, the cyber fortune-teller, asks you a series of questions. There are no "
"wrong answers: your replies shape your starting statistics.\n\n"
"Enter your name on the letter grid. Move with the D-pad, press Circle to add a "
"letter and Cross to delete one, and press Start when you are done. L1 and R1 "
"scroll the grid; further down there are kana if you want a Japanese name.\n\n"
"Soon after the opening you choose a partner. Who you bring along changes the "
"story, the help you get, and which ending you will see."},
{"Exploring",
"The game is played in first person. Up and Down on the D-pad walk forward and "
"back; Left and Right turn on the spot.\n\n"
"Press Circle to open the command bar:\n"
"  COMP    - the demon-summoning program on your Arm Terminal: call, return or "
"remove allies, analyze demons, auto-map and more.\n"
"  MAGIC   - cast spells outside battle (healing, mapping, warding).\n"
"  ITEM    - use, sort, tidy or throw away items.\n"
"  EQUIP   - swords, guns, ammunition and armor for head, body, arms and legs.\n"
"  STATUS  - full statistics; L1 and R1 switch between characters.\n"
"  CHANGE  - the party's marching order.\n"
"Press Triangle on a command to read what it does.\n\n"
"The top of the screen shows the phase of the moon, the direction you face, your "
"Magnetite (MAG) and your money (macca).\n\n"
"Press Start for the system menu: quick save, load and the game's own settings "
"(message speed, battle effects, auto-battle, map orientation, stereo/mono)."},
{"The moon",
"The moon waxes and wanes as you walk, through eight phases from new moon to full "
"moon. Demons are calmest under a new moon. As the moon fills they grow more "
"aggressive, and at full moon many of them will hardly listen to anything you "
"say. Some events and fusions only work during certain phases."},
{"Battle",
"Demons appear as you explore. At the start of a fight you choose to Fight, "
"Talk, Escape, run Auto-battle, Summon an ally, or change settings.\n\n"
"In a fight each character picks an action: a sword strike, a gun shot (it "
"needs ammunition loaded), a normal or special attack, Magic, an Item, Guard, or "
"returning a demon to the COMP. The battle message speed and effects can be "
"changed from the settings entry.\n\n"
"Each demon has its own strengths and weaknesses. Analyze a demon you have "
"beaten to read them, and match your attacks to the weak spots."},
{"Talking to demons",
"Instead of fighting, you can Talk. Demons have moods and personalities: they "
"may ask for money, an item, Magnetite or a bit of your health, quiz you, tease "
"you, or simply leave. Answer well and a demon may agree to join you as an ally.\n\n"
"Allies are stored in the COMP and summoned when you need them. Summoned allies "
"use up Magnetite while you walk; if your MAG runs out they start to suffer. "
"Demons whose outlook (Law, Neutral or Chaos) is too far from yours may refuse "
"to work with you."},
{"Fusion",
"At the Cathedral of Shadows you can fuse two or three of your allies into a "
"single, usually stronger, demon. The result depends on the races of the demons "
"you combine, and you cannot create a demon whose level is beyond your own.\n\n"
"Swords can be fused too: combine a sword with a demon (or two swords and a "
"demon) to forge a new weapon that carries some of the demon's power."},
{"Growing stronger",
"Winning fights earns experience; each level up raises your statistics:\n"
"  St  Strength   - sword and physical damage\n"
"  In  Intelligence - magic and talking\n"
"  Ma  Magic      - spell power and MP\n"
"  Vi  Vitality   - HP and defense\n"
"  Ag  Agility    - turn order, accuracy and evasion\n"
"  Lu  Luck       - a little of everything\n\n"
"Your character is also watched over by a guardian spirit, shown on the STATUS "
"screen. The guardian shapes how you grow and which magic you can use, and it "
"can change as the story goes on."},
{"Saving",
"The game saves to a virtual memory card. Look for the places in the school "
"where you can record your progress, and use the quick save on the Start menu "
"when you need to stop somewhere else (a quick save is removed once you resume "
"from it).\n\n"
"This native build also has save states: open this menu (F1) and choose Save "
"States, or press F7 / Select + R1 for the runtime's own slot browser. A save "
"state captures the exact moment, so use it alongside the game's own saves, not "
"instead of them."},
{"Tips",
"- Talk to everyone in the school: students and teachers explain how things work.\n"
"- Keep some healing items and money in reserve; demons often ask for both.\n"
"- Check your Magnetite before summoning a large party.\n"
"- Analyze new demons: knowing a weakness can turn a hard fight around.\n"
"- If a corridor seems endless, look at the auto-map in the COMP."},
{"About this edition",
"This is a fan translation of Shin Megami Tensei if... (PlayStation, Anniversary "
"Pack disc), played through a static recompilation built with PSXRecomp.\n\n"
"Translated so far: the opening and the school chapter's script, every menu, "
"item, demon, spell and race name, battle messages, demon conversation menus "
"and results, status and level-up screens, the name entry grid, and the intro "
"movie's text scroll. Later chapters, and the longer lines demons say while you "
"negotiate, are still in Japanese.\n\n"
"Shin Megami Tensei if... is (c) ATLUS. This guide was written for the fan "
"translation and is not the original manual."},
};

// What each button does in SMT if..., checked in the game.
static const PadButton kPad[] = {
    {PSX_KB_UP, "Up", "Walk forward / move cursor"},
    {PSX_KB_DOWN, "Down", "Step back / move cursor"},
    {PSX_KB_LEFT, "Left", "Turn left"},
    {PSX_KB_RIGHT, "Right", "Turn right"},
    {PSX_KB_CIRCLE, "Circle", "Confirm, talk, open the command bar"},
    {PSX_KB_CROSS, "Cross", "Cancel / back"},
    {PSX_KB_TRIANGLE, "Triangle", "Explain the highlighted command"},
    {PSX_KB_SQUARE, "Square", "Cancel / close menus"},
    {PSX_KB_L1, "L1", "Previous character / page"},
    {PSX_KB_R1, "R1", "Next character / page"},
    {PSX_KB_L2, "L2", "(not used while exploring)"},
    {PSX_KB_R2, "R2", "(not used while exploring)"},
    {PSX_KB_START, "Start", "System menu: quick save, load, settings"},
    {PSX_KB_SELECT, "Select", "(not used while exploring)"},
};
