// game_menu.cpp -- in-game menu for PSXRecomp native builds (SMT Recomp kit).
//
// A PsxMenuProvider (runtime/include/psx_menu_host.h) drawn with Dear ImGui over the
// game picture. Pages: Resume, Save States, Controls (diagram), Key Bindings,
// Manual, Quit. The game-specific text (title, guide, what each button does) is in
// game_menu_content.h. Opens with F1 (keyboard) or Select + L3 / the Home button (controller).
//
// Threads (per psx_menu_host.h): attach/event/is_open/set_open run on the main
// thread, draw on the thread that owns the GL context. The two share state under
// g_mu; ImGui itself is only touched from draw. Input reaches ImGui through a small
// queue filled by event(). Save/load requests and key rebinds run on the main thread.
#include "psx_menu_host.h"
#include "psx_keybinds.h"   // pulls in psx_sdl.h (SDL3 or SDL2 shim)
#include "savestate.h"
#include "host_osd.h"

#include "imgui.h"
#include "imgui_impl_opengl3.h"

#if defined(__APPLE__)
#define GL_SILENCE_DEPRECATION 1
#include <OpenGL/gl.h>
#elif defined(_WIN32)
#include <windows.h>
#include <GL/gl.h>
#else
#include <GL/gl.h>
#endif

#include <algorithm>
#include <atomic>
#include <cfloat>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <mutex>
#include <string>
#include <vector>

namespace {

// ------------------------------------------------------------------ shared state
std::mutex g_mu;
const PsxMenuHost *g_host = nullptr;
SDL_Window *g_window = nullptr;
bool g_open = false;
int g_page = 0;
int g_win_w = 1280, g_win_h = 960;          // window size in points (main thread)
int g_rebind = -1;                         // button waiting for a key, -1 = none
std::string g_status;                      // footer message
bool g_refresh_slots = true;               // re-read slot info + thumbnails
int g_pending_action = 0;                  // 1 = save, 2 = load (main thread runs it)
int g_pending_slot = -1;
bool g_quit_confirm = false;
unsigned g_pad_held = 0;                   // controller buttons held (bit = SDL button)

struct QEvent { int kind; int a; float x, y; bool down; };   // queued for ImGui
std::vector<QEvent> g_queue;
enum { Q_KEY = 1, Q_MOUSE_POS, Q_MOUSE_BTN, Q_WHEEL, Q_PAD };

// ------------------------------------------------------------------ GL-thread state
ImGuiContext *g_ctx = nullptr;
bool g_gl_ready = false;
uint64_t g_last_ticks = 0;
ImFont *g_font = nullptr, *g_font_big = nullptr;
float g_font_px = 0;

constexpr int kSlots = 10;
struct SlotInfo { bool exists = false; std::string when; GLuint tex = 0; };
SlotInfo g_slots[kSlots];

// ------------------------------------------------------------------ text
const char *kPages[] = {"Resume", "Save States", "Controls", "Key Bindings", "Manual", "Quit Game"};
enum { P_RESUME, P_STATES, P_CONTROLS, P_BINDS, P_MANUAL, P_QUIT, P_COUNT };

struct ManualSection { const char *title; const char *body; };
struct PadButton { int kb; const char *name; const char *action; };
#include "game_menu_content.h"   // GM_TITLE, GM_PROVIDER_NAME, kManual[], kPad[]
constexpr int kManualCount = sizeof(kManual) / sizeof(kManual[0]);
int g_manual = 0;

std::string key_name(SDL_Scancode sc) {
    if (sc == SDL_SCANCODE_UNKNOWN) return "-";
    if (PSXKB_IS_MOUSE_SC(sc)) return "Mouse" + std::to_string((int)sc - PSXKB_MOUSE_SC_BASE);
    const char *n = SDL_GetScancodeName(sc);
    return (n && *n) ? n : "?";
}

std::string binding_text(int kb) {
    std::string s = key_name(psx_keybinds_get_button(1, kb));
    SDL_Scancode alt = psx_keybinds_get_button_alt(1, kb);
    if (alt != SDL_SCANCODE_UNKNOWN) s += " / " + key_name(alt);
    return s;
}

// ------------------------------------------------------------------ open / close
void open_locked(bool open) {
    if (open == g_open) return;
    g_open = open;
    g_rebind = -1;
    g_quit_confirm = false;
    if (open) {
        g_refresh_slots = true;
        g_status.clear();
    }
    if (g_host && g_host->set_paused) g_host->set_paused(open ? 1 : 0);
}

void queue(int kind, int a, float x = 0, float y = 0, bool down = false) {
    g_queue.push_back({kind, a, x, y, down});
}

ImGuiKey imgui_key(SDL_Keycode k) {
    switch (k) {
    case SDLK_UP: return ImGuiKey_UpArrow;
    case SDLK_DOWN: return ImGuiKey_DownArrow;
    case SDLK_LEFT: return ImGuiKey_LeftArrow;
    case SDLK_RIGHT: return ImGuiKey_RightArrow;
    case SDLK_RETURN: case SDLK_KP_ENTER: return ImGuiKey_Enter;
    case SDLK_SPACE: return ImGuiKey_Space;
    case SDLK_TAB: return ImGuiKey_Tab;
    case SDLK_PAGEUP: return ImGuiKey_PageUp;
    case SDLK_PAGEDOWN: return ImGuiKey_PageDown;
    case SDLK_HOME: return ImGuiKey_Home;
    case SDLK_END: return ImGuiKey_End;
    case SDLK_BACKSPACE: return ImGuiKey_Backspace;
    default: return ImGuiKey_None;
    }
}

#if defined(PSX_SDL3)
ImGuiKey imgui_pad(int b) {
    switch (b) {
    case SDL_GAMEPAD_BUTTON_DPAD_UP: return ImGuiKey_GamepadDpadUp;
    case SDL_GAMEPAD_BUTTON_DPAD_DOWN: return ImGuiKey_GamepadDpadDown;
    case SDL_GAMEPAD_BUTTON_DPAD_LEFT: return ImGuiKey_GamepadDpadLeft;
    case SDL_GAMEPAD_BUTTON_DPAD_RIGHT: return ImGuiKey_GamepadDpadRight;
    case SDL_GAMEPAD_BUTTON_SOUTH: return ImGuiKey_GamepadFaceDown;
    case SDL_GAMEPAD_BUTTON_EAST: return ImGuiKey_GamepadFaceRight;
    case SDL_GAMEPAD_BUTTON_WEST: return ImGuiKey_GamepadFaceLeft;
    case SDL_GAMEPAD_BUTTON_NORTH: return ImGuiKey_GamepadFaceUp;
    case SDL_GAMEPAD_BUTTON_LEFT_SHOULDER: return ImGuiKey_GamepadL1;
    case SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER: return ImGuiKey_GamepadR1;
    default: return ImGuiKey_None;
    }
}
#endif

// ------------------------------------------------------------------ provider: main thread
// The program's folder, with a trailing separator ("" if unknown).
std::string exe_dir() {
#if defined(PSX_SDL3)
    const char *b = SDL_GetBasePath();          // owned by SDL3
    return b ? std::string(b) : std::string();
#else
    char *b = SDL_GetBasePath();                // SDL2: caller frees
    std::string s = b ? b : "";
    if (b) SDL_free(b);
    return s;
#endif
}

int p_attach(void *, void *sdl_window, void *, const PsxMenuHost *host) {
    std::lock_guard<std::mutex> lk(g_mu);
    g_host = host;
    g_window = static_cast<SDL_Window *>(sdl_window);
    if (g_window) SDL_GetWindowSize(g_window, &g_win_w, &g_win_h);
    // The runtime derives keybinds.ini from argv[0]; a program name without an
    // extension (macOS, Linux) is taken for a folder, so the file is never read or
    // written. Point it at the program's folder: this loads saved bindings and makes
    // Key Bindings changes stick.
    static bool binds_ready = false;
    if (!binds_ready) {
        binds_ready = true;
        const std::string dir = exe_dir();
        if (!dir.empty()) psx_keybinds_init(dir.c_str());
    }
    return 1;
}

int p_event(void *, const void *p) {
    if (!p) return 0;
    const SDL_Event &e = *static_cast<const SDL_Event *>(p);
    std::lock_guard<std::mutex> lk(g_mu);
#if defined(PSX_SDL3)
    if (e.type == SDL_EVENT_WINDOW_RESIZED || e.type == SDL_EVENT_WINDOW_PIXEL_SIZE_CHANGED) {
        if (g_window) SDL_GetWindowSize(g_window, &g_win_w, &g_win_h);
        return 0;
    }
    if (e.type == SDL_EVENT_KEY_DOWN) {
        const SDL_Keycode k = e.key.key;
        const SDL_Scancode sc = e.key.scancode;
        if (g_open && g_rebind >= 0) {             // capturing a key for a rebind
            if (!e.key.repeat) {
                if (k == SDLK_ESCAPE) {
                    g_status = "Rebind cancelled.";
                } else {
                    psx_keybinds_set_button(1, g_rebind, k == SDLK_BACKSPACE ? SDL_SCANCODE_UNKNOWN : sc);
                    psx_keybinds_save();
                    g_status = std::string(psx_keybinds_button_label(g_rebind)) + " is now " +
                               key_name(psx_keybinds_get_button(1, g_rebind)) + ".";
                }
                g_rebind = -1;
            }
            return 1;
        }
        if (!e.key.repeat && k == SDLK_F1) {
            open_locked(!g_open);
            return 1;
        }
        if (!g_open) return 0;
        if (!e.key.repeat && k == SDLK_ESCAPE) {
            open_locked(false);
            return 1;
        }
        const ImGuiKey ik = imgui_key(k);
        if (ik != ImGuiKey_None) queue(Q_KEY, ik, 0, 0, true);
        return 1;
    }
    if (e.type == SDL_EVENT_KEY_UP) {
        if (!g_open) return 0;
        const ImGuiKey ik = imgui_key(e.key.key);
        if (ik != ImGuiKey_None) queue(Q_KEY, ik, 0, 0, false);
        return 1;
    }
    if (e.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN || e.type == SDL_EVENT_GAMEPAD_BUTTON_UP) {
        const bool down = e.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN;
        const unsigned bit = 1u << e.gbutton.button;
        const unsigned before = g_pad_held;
        g_pad_held = down ? (g_pad_held | bit) : (g_pad_held & ~bit);
        const unsigned combo = (1u << SDL_GAMEPAD_BUTTON_BACK) | (1u << SDL_GAMEPAD_BUTTON_LEFT_STICK);
        if (down && (((g_pad_held & combo) == combo && (before & combo) != combo) ||
                     e.gbutton.button == SDL_GAMEPAD_BUTTON_GUIDE)) {
            open_locked(!g_open);
            return 1;
        }
        if (!g_open) return 0;
        if (down && e.gbutton.button == SDL_GAMEPAD_BUTTON_START) {
            open_locked(false);
            return 1;
        }
        const ImGuiKey ik = imgui_pad(e.gbutton.button);
        if (ik != ImGuiKey_None) queue(Q_PAD, ik, 0, 0, down);
        return 1;
    }
    if (!g_open) return 0;
    switch (e.type) {
    case SDL_EVENT_MOUSE_MOTION:
        queue(Q_MOUSE_POS, 0, e.motion.x, e.motion.y);
        return 1;
    case SDL_EVENT_MOUSE_BUTTON_DOWN:
    case SDL_EVENT_MOUSE_BUTTON_UP: {
        int b = e.button.button == SDL_BUTTON_LEFT ? 0 : e.button.button == SDL_BUTTON_RIGHT ? 1 : 2;
        queue(Q_MOUSE_POS, 0, e.button.x, e.button.y);
        queue(Q_MOUSE_BTN, b, 0, 0, e.type == SDL_EVENT_MOUSE_BUTTON_DOWN);
        return 1;
    }
    case SDL_EVENT_MOUSE_WHEEL:
        queue(Q_WHEEL, 0, e.wheel.x, e.wheel.y);
        return 1;
    case SDL_EVENT_TEXT_INPUT: case SDL_EVENT_GAMEPAD_AXIS_MOTION:
        return 1;
    default:
        return 0;
    }
#else
    (void)e;
    return 0;   // SDL2 builds: the menu is not wired up
#endif
}

int p_is_open(void *) {
    // Main thread, every frame: also the place where queued save/load requests run.
    std::lock_guard<std::mutex> lk(g_mu);
    if (g_pending_action) {
        const int slot = g_pending_slot;
        const bool save = g_pending_action == 1;
        g_pending_action = 0;
        open_locked(false);
        char msg[96];
        if (savestate_title_blocked()) {
            host_osd_push("Save states are unavailable right now", 1800);
        } else if (save ? savestate_request_save(slot) : savestate_request_load(slot)) {
            std::snprintf(msg, sizeof msg, "%s slot %d...", save ? "Saving to" : "Loading", slot + 1);
            host_osd_push(msg, 1200);
        } else {
            std::snprintf(msg, sizeof msg, "Could not %s slot %d", save ? "save to" : "load", slot + 1);
            host_osd_push(msg, 1800);
        }
    }
    return g_open ? 1 : 0;
}

void p_set_open(void *, int open) {
    std::lock_guard<std::mutex> lk(g_mu);
    open_locked(open != 0);
}

// ------------------------------------------------------------------ drawing helpers (GL thread)
ImU32 col(int r, int g, int b, int a = 255) { return IM_COL32(r, g, b, a); }

void style_setup() {
    ImGuiStyle &s = ImGui::GetStyle();
    s.WindowRounding = 6; s.FrameRounding = 4; s.GrabRounding = 4; s.ChildRounding = 4;
    s.WindowBorderSize = 1; s.FrameBorderSize = 0;
    s.WindowPadding = ImVec2(18, 16); s.FramePadding = ImVec2(10, 6); s.ItemSpacing = ImVec2(10, 8);
    ImVec4 *c = s.Colors;
    c[ImGuiCol_WindowBg] = ImVec4(0.04f, 0.10f, 0.11f, 0.96f);
    c[ImGuiCol_ChildBg] = ImVec4(0.03f, 0.07f, 0.08f, 0.85f);
    c[ImGuiCol_Border] = ImVec4(0.20f, 0.45f, 0.45f, 0.80f);
    c[ImGuiCol_Text] = ImVec4(0.88f, 0.94f, 0.92f, 1.00f);
    c[ImGuiCol_TextDisabled] = ImVec4(0.50f, 0.62f, 0.60f, 1.00f);
    c[ImGuiCol_Button] = ImVec4(0.10f, 0.26f, 0.28f, 1.00f);
    c[ImGuiCol_ButtonHovered] = ImVec4(0.16f, 0.40f, 0.42f, 1.00f);
    c[ImGuiCol_ButtonActive] = ImVec4(0.22f, 0.52f, 0.54f, 1.00f);
    c[ImGuiCol_Header] = ImVec4(0.12f, 0.30f, 0.32f, 1.00f);
    c[ImGuiCol_HeaderHovered] = ImVec4(0.18f, 0.42f, 0.44f, 1.00f);
    c[ImGuiCol_HeaderActive] = ImVec4(0.24f, 0.54f, 0.56f, 1.00f);
    c[ImGuiCol_FrameBg] = ImVec4(0.08f, 0.18f, 0.19f, 1.00f);
    c[ImGuiCol_Separator] = ImVec4(0.20f, 0.45f, 0.45f, 0.60f);
    c[ImGuiCol_NavCursor] = ImVec4(0.95f, 0.35f, 0.25f, 1.00f);
    c[ImGuiCol_ScrollbarGrab] = ImVec4(0.18f, 0.40f, 0.42f, 1.00f);
}

void load_fonts(float px) {
    ImGuiIO &io = ImGui::GetIO();
    io.Fonts->Clear();
    g_font = g_font_big = nullptr;
    std::string dir = (g_host && g_host->assets_dir) ? g_host->assets_dir : "assets";
    const std::string reg = dir + "/fonts/LatoLatin-Regular.ttf";
    const std::string bold = dir + "/fonts/LatoLatin-Bold.ttf";
    if (FILE *f = std::fopen(reg.c_str(), "rb")) {
        std::fclose(f);
        g_font = io.Fonts->AddFontFromFileTTF(reg.c_str(), px);
        FILE *fb = std::fopen(bold.c_str(), "rb");
        if (fb) { std::fclose(fb); g_font_big = io.Fonts->AddFontFromFileTTF(bold.c_str(), px * 1.45f); }
    }
    if (!g_font) {
        ImFontConfig cfg; cfg.SizePixels = px;
        g_font = io.Fonts->AddFontDefault(&cfg);
    }
    if (!g_font_big) g_font_big = g_font;
    g_font_px = px;
}

void refresh_slots() {
    for (int i = 0; i < kSlots; ++i) {
        SlotInfo &s = g_slots[i];
        s.exists = savestate_slot_exists(i) != 0;
        s.when.clear();
        int64_t t = 0;
        if (s.exists && savestate_slot_mtime(i, &t)) {
            time_t tt = (time_t)t;
            char buf[64];
            std::strftime(buf, sizeof buf, "%b %d  %H:%M", std::localtime(&tt));
            s.when = buf;
        }
        if (s.tex) { glDeleteTextures(1, &s.tex); s.tex = 0; }
        if (!s.exists) continue;
        const int w = SAVESTATE_THUMB_W, h = SAVESTATE_THUMB_H;
        std::vector<uint32_t> argb(w * h);
        if (!savestate_read_thumb(i, argb.data(), w, h)) continue;
        std::vector<uint8_t> rgba(w * h * 4);
        for (int k = 0; k < w * h; ++k) {
            const uint32_t v = argb[k];
            rgba[k * 4 + 0] = (v >> 16) & 255; rgba[k * 4 + 1] = (v >> 8) & 255;
            rgba[k * 4 + 2] = v & 255; rgba[k * 4 + 3] = 255;
        }
        glGenTextures(1, &s.tex);
        glBindTexture(GL_TEXTURE_2D, s.tex);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
        glPixelStorei(GL_UNPACK_ALIGNMENT, 1);
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, w, h, 0, GL_RGBA, GL_UNSIGNED_BYTE, rgba.data());
    }
}

// --- pages
void page_states(float u) {
    ImGui::TextDisabled("Save states capture this exact moment. Keep using the game's own saves too.");
    const float th = 54 * u, tw = th * 4 / 3;
    if (ImGui::BeginTable("slots", 3, ImGuiTableFlags_RowBg | ImGuiTableFlags_BordersInnerH | ImGuiTableFlags_ScrollY,
                          ImVec2(0, -ImGui::GetTextLineHeightWithSpacing()))) {
        ImGui::TableSetupColumn("pic", ImGuiTableColumnFlags_WidthFixed, tw + 4 * u);
        ImGui::TableSetupColumn("info", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableSetupColumn("act", ImGuiTableColumnFlags_WidthFixed, 130 * u);
        for (int i = 0; i < kSlots; ++i) {
            const SlotInfo &s = g_slots[i];
            ImGui::PushID(i);
            ImGui::TableNextRow(0, th + 6 * u);
            ImGui::TableNextColumn();
            ImVec2 p = ImGui::GetCursorScreenPos();
            if (s.tex) {
                ImGui::Image((ImTextureID)(intptr_t)s.tex, ImVec2(tw, th));
            } else {
                ImGui::GetWindowDrawList()->AddRectFilled(p, ImVec2(p.x + tw, p.y + th), col(8, 22, 24));
                ImGui::GetWindowDrawList()->AddRect(p, ImVec2(p.x + tw, p.y + th), col(40, 90, 90));
                ImGui::Dummy(ImVec2(tw, th));
            }
            ImGui::TableNextColumn();
            ImGui::PushFont(g_font_big);
            ImGui::Text("Slot %d", i + 1);
            ImGui::PopFont();
            ImGui::TextDisabled("%s", s.exists ? s.when.c_str() : "Empty");
            ImGui::TableNextColumn();
            if (ImGui::Button("Save", ImVec2(60 * u, 0))) { g_pending_action = 1; g_pending_slot = i; }
            ImGui::SameLine();
            ImGui::BeginDisabled(!s.exists);
            if (ImGui::Button("Load", ImVec2(60 * u, 0))) { g_pending_action = 2; g_pending_slot = i; }
            ImGui::EndDisabled();
            ImGui::PopID();
        }
        ImGui::EndTable();
    }
    ImGui::TextDisabled("F7 or Select + R1 opens the runtime's own slot browser.");
}

// Stylised PlayStation controller, labelled, with a table of keys and actions below.
void pad_table(float u) {
    if (ImGui::BeginTable("pad", 3, ImGuiTableFlags_RowBg | ImGuiTableFlags_BordersInnerH)) {
        ImGui::TableSetupColumn("Button", ImGuiTableColumnFlags_WidthFixed, 80 * u);
        ImGui::TableSetupColumn("Key", ImGuiTableColumnFlags_WidthFixed, 110 * u);
        ImGui::TableSetupColumn("In the game", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableHeadersRow();
        for (const PadButton &pb : kPad) {
            ImGui::TableNextRow();
            ImGui::TableNextColumn(); ImGui::TextUnformatted(pb.name);
            ImGui::TableNextColumn(); ImGui::TextColored(ImVec4(0.95f, 0.75f, 0.45f, 1), "%s", binding_text(pb.kb).c_str());
            ImGui::TableNextColumn(); ImGui::TextWrapped("%s", pb.action);
        }
        ImGui::EndTable();
    }
}

void page_controls(float u) {
    ImGui::BeginChild("ctl", ImVec2(0, 0), ImGuiChildFlags_None);
    ImDrawList *dl = ImGui::GetWindowDrawList();
    const ImVec2 o = ImGui::GetCursorScreenPos();
    const float W = ImGui::GetContentRegionAvail().x;
    const float cw = std::min(W * 0.9f, 430 * u), ch = cw * 0.55f;
    const ImVec2 c(o.x + W * 0.5f, o.y + ch * 0.84f);
    auto P = [&](float x, float y) { return ImVec2(c.x + x * cw, c.y + y * ch); };
    const ImU32 body = col(208, 212, 214), shade = col(176, 181, 184), dark = col(64, 68, 72), lab = col(20, 40, 42);
    auto label = [&](ImVec2 at, const char *t, ImU32 cl) {
        const ImVec2 sz = ImGui::CalcTextSize(t);
        dl->AddText(ImVec2(at.x - sz.x * 0.5f, at.y - sz.y * 0.5f), cl, t);
    };
    // shoulders (L2/R2 behind L1/R1)
    dl->AddRectFilled(P(-0.42f, -0.80f), P(-0.20f, -0.64f), col(150, 155, 158), 6 * u);
    dl->AddRectFilled(P(0.20f, -0.80f), P(0.42f, -0.64f), col(150, 155, 158), 6 * u);
    dl->AddRectFilled(P(-0.42f, -0.66f), P(-0.20f, -0.52f), shade, 6 * u);
    dl->AddRectFilled(P(0.20f, -0.66f), P(0.42f, -0.52f), shade, 6 * u);
    label(P(-0.31f, -0.725f), "L2", lab); label(P(0.31f, -0.725f), "R2", lab);
    label(P(-0.31f, -0.59f), "L1", lab); label(P(0.31f, -0.59f), "R1", lab);
    // grips and body
    dl->AddCircleFilled(P(-0.33f, 0.28f), ch * 0.40f, body, 48);
    dl->AddCircleFilled(P(0.33f, 0.28f), ch * 0.40f, body, 48);
    dl->AddRectFilled(P(-0.47f, -0.54f), P(0.47f, 0.20f), body, 30 * u);
    // d-pad
    const ImVec2 dp = P(-0.30f, -0.17f);
    const float a = ch * 0.075f, b = ch * 0.21f;
    dl->AddRectFilled(ImVec2(dp.x - a, dp.y - b), ImVec2(dp.x + a, dp.y + b), dark, 3);
    dl->AddRectFilled(ImVec2(dp.x - b, dp.y - a), ImVec2(dp.x + b, dp.y + a), dark, 3);
    // face buttons
    const ImVec2 fb = P(0.30f, -0.17f);
    const float r = ch * 0.08f, d = ch * 0.18f;
    const ImVec2 tri(fb.x, fb.y - d), cir(fb.x + d, fb.y), crs(fb.x, fb.y + d), sqr(fb.x - d, fb.y);
    for (ImVec2 q : {tri, cir, crs, sqr}) dl->AddCircleFilled(q, r, dark, 32);
    const float t = std::max(1.5f, 2 * u);
    dl->AddTriangle(ImVec2(tri.x, tri.y - r * 0.55f), ImVec2(tri.x - r * 0.5f, tri.y + r * 0.35f),
                    ImVec2(tri.x + r * 0.5f, tri.y + r * 0.35f), col(80, 210, 170), t);
    dl->AddCircle(cir, r * 0.5f, col(240, 90, 90), 32, t);
    dl->AddLine(ImVec2(crs.x - r * 0.45f, crs.y - r * 0.45f), ImVec2(crs.x + r * 0.45f, crs.y + r * 0.45f), col(120, 160, 240), t);
    dl->AddLine(ImVec2(crs.x + r * 0.45f, crs.y - r * 0.45f), ImVec2(crs.x - r * 0.45f, crs.y + r * 0.45f), col(120, 160, 240), t);
    dl->AddRect(ImVec2(sqr.x - r * 0.42f, sqr.y - r * 0.42f), ImVec2(sqr.x + r * 0.42f, sqr.y + r * 0.42f), col(230, 130, 200), 0, 0, t);
    // select / start and sticks
    const ImVec2 sel = P(-0.09f, -0.17f), sta = P(0.09f, -0.17f);
    dl->AddRectFilled(ImVec2(sel.x - 10 * u, sel.y - 4 * u), ImVec2(sel.x + 10 * u, sel.y + 4 * u), dark, 4 * u);
    dl->AddTriangleFilled(ImVec2(sta.x - 8 * u, sta.y - 6 * u), ImVec2(sta.x - 8 * u, sta.y + 6 * u), ImVec2(sta.x + 9 * u, sta.y), dark);
    label(ImVec2(sel.x, sel.y + 14 * u), "SELECT", lab); label(ImVec2(sta.x, sta.y + 14 * u), "START", lab);
    dl->AddCircleFilled(P(-0.15f, 0.17f), ch * 0.10f, col(60, 64, 68), 32);
    dl->AddCircleFilled(P(0.15f, 0.17f), ch * 0.10f, col(60, 64, 68), 32);
    // the four most-used actions, written on the pad
    ImGui::Dummy(ImVec2(W, ch * 1.58f));
    pad_table(u);
    ImGui::Spacing();
    ImGui::TextWrapped("Keys are your keyboard bindings (change them on the Key Bindings page). Controllers work "
                       "automatically in the PlayStation layout: bottom = Cross, right = Circle, left = Square, "
                       "top = Triangle.");
    ImGui::TextDisabled("Native build keys: F1 this menu, F7 save-state browser, Tab fast-forward (hold), "
                        "Alt+Enter fullscreen.");
    ImGui::EndChild();
}

void page_binds(float u) {
    ImGui::TextWrapped("Choose a button, then press the key you want for it. Esc cancels, Backspace clears. "
                       "Changes apply at once and are saved to keybinds.ini.");
    ImGui::Spacing();
    if (ImGui::BeginTable("binds", 3, ImGuiTableFlags_RowBg | ImGuiTableFlags_BordersInnerH)) {
        ImGui::TableSetupColumn("Button", ImGuiTableColumnFlags_WidthFixed, 80 * u);
        ImGui::TableSetupColumn("Key", ImGuiTableColumnFlags_WidthFixed, 140 * u);
        ImGui::TableSetupColumn("In the game", ImGuiTableColumnFlags_WidthStretch);
        for (const PadButton &pb : kPad) {
            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::TextUnformatted(pb.name);
            ImGui::TableNextColumn();
            ImGui::PushID(pb.kb);
            std::string lab = g_rebind == pb.kb ? std::string("Press a key...") : binding_text(pb.kb);
            if (ImGui::Button(lab.c_str(), ImVec2(130 * u, 0))) {
                g_rebind = pb.kb;
                g_status = std::string("Press a key for ") + pb.name + " (Esc cancels).";
            }
            ImGui::PopID();
            ImGui::TableNextColumn();
            ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled));
            ImGui::TextWrapped("%s", pb.action);
            ImGui::PopStyleColor();
        }
        ImGui::EndTable();
    }
    ImGui::Spacing();
    if (ImGui::Button("Reset to defaults")) {
        g_pending_action = 3;   // done on the main thread
    }
    ImGui::SameLine();
    ImGui::TextDisabled("Controller buttons are mapped automatically.");
}

void page_manual(float u) {
    ImGui::BeginChild("toc", ImVec2(std::max(120 * u, ImGui::GetContentRegionAvail().x * 0.30f), 0), ImGuiChildFlags_Borders);
    for (int i = 0; i < kManualCount; ++i)
        if (ImGui::Selectable(kManual[i].title, g_manual == i)) g_manual = i;
    ImGui::EndChild();
    ImGui::SameLine();
    ImGui::BeginChild("text", ImVec2(0, 0), ImGuiChildFlags_Borders);
    ImGui::PushFont(g_font_big);
    ImGui::TextUnformatted(kManual[g_manual].title);
    ImGui::PopFont();
    ImGui::Separator();
    ImGui::PushTextWrapPos(0);
    ImGui::TextUnformatted(kManual[g_manual].body);
    ImGui::PopTextWrapPos();
    ImGui::EndChild();
}

void page_quit(float) {
    ImGui::TextWrapped("Quit the game? Anything you haven't saved will be lost.");
    ImGui::Spacing();
    if (ImGui::Button("Quit to desktop")) {
        if (g_host && g_host->request_exit) g_host->request_exit(PSX_MENU_EXIT_QUIT);
    }
    ImGui::SameLine();
    if (ImGui::Button("Cancel")) g_page = P_RESUME;
}

// ------------------------------------------------------------------ provider: GL thread
void p_draw(void *, int fb_w, int fb_h) {
    std::vector<QEvent> evs;
    int win_w, win_h;
    {
        std::lock_guard<std::mutex> lk(g_mu);
        if (!g_open || fb_w <= 0 || fb_h <= 0) { g_queue.clear(); return; }
        evs.swap(g_queue);
        win_w = g_win_w > 0 ? g_win_w : fb_w;
        win_h = g_win_h > 0 ? g_win_h : fb_h;
    }
    ImGuiContext *prev = ImGui::GetCurrentContext();
    if (!g_ctx) {
        g_ctx = ImGui::CreateContext();
        ImGui::SetCurrentContext(g_ctx);
        ImGuiIO &io = ImGui::GetIO();
        io.IniFilename = nullptr;
        io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
        io.BackendFlags |= ImGuiBackendFlags_HasGamepad;
        style_setup();
    }
    ImGui::SetCurrentContext(g_ctx);
    ImGuiIO &io = ImGui::GetIO();
    const float u = std::min(3.0f, std::max(0.75f, win_h / 600.0f));   // UI scale in points
    const float want_px = std::round(19.0f * u * (float)fb_h / (float)win_h);
    if (want_px != g_font_px) {
        if (g_gl_ready) ImGui_ImplOpenGL3_DestroyFontsTexture();
        load_fonts(want_px);
        io.FontGlobalScale = (float)win_h / (float)fb_h;      // fonts rasterised at pixel size
    }
    if (!g_gl_ready) g_gl_ready = ImGui_ImplOpenGL3_Init(nullptr);
    if (!g_gl_ready) { ImGui::SetCurrentContext(prev); return; }
    io.DisplaySize = ImVec2((float)win_w, (float)win_h);
    io.DisplayFramebufferScale = ImVec2((float)fb_w / win_w, (float)fb_h / win_h);
    const uint64_t now = SDL_GetTicks();
    io.DeltaTime = g_last_ticks && now > g_last_ticks ? (now - g_last_ticks) / 1000.0f : 1.0f / 60.0f;
    g_last_ticks = now;
    for (const QEvent &q : evs) {
        switch (q.kind) {
        case Q_KEY: case Q_PAD: io.AddKeyEvent((ImGuiKey)q.a, q.down); break;
        case Q_MOUSE_POS: io.AddMousePosEvent(q.x, q.y); break;
        case Q_MOUSE_BTN: io.AddMouseButtonEvent(q.a, q.down); break;
        case Q_WHEEL: io.AddMouseWheelEvent(q.x, q.y); break;
        }
    }

    bool refresh = false;
    {
        std::lock_guard<std::mutex> lk(g_mu);
        refresh = g_refresh_slots;
        g_refresh_slots = false;
    }
    if (refresh) refresh_slots();

    ImGui_ImplOpenGL3_NewFrame();
    ImGui::NewFrame();
    // dim the game
    ImGui::GetBackgroundDrawList()->AddRectFilled(ImVec2(0, 0), io.DisplaySize, col(0, 0, 0, 150));
    const ImVec2 size(std::min(io.DisplaySize.x - 16 * u, 1180 * u), std::min(io.DisplaySize.y - 16 * u, 760 * u));
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(size, ImGuiCond_Always);
    ImGui::Begin("##smtif_menu", nullptr, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_NoMove |
                                             ImGuiWindowFlags_NoSavedSettings);
    ImGui::PushFont(g_font_big);
    ImGui::TextColored(ImVec4(0.95f, 0.40f, 0.30f, 1), "%s", GM_TITLE);
    ImGui::PopFont();
    ImGui::SameLine();
    ImGui::TextDisabled("  game paused  -  F1 / Esc to resume");
    ImGui::Separator();

    std::lock_guard<std::mutex> lk(g_mu);
    ImGui::BeginChild("nav", ImVec2(150 * u, -ImGui::GetFrameHeightWithSpacing()), ImGuiChildFlags_None);
    for (int i = 0; i < P_COUNT; ++i) {
        if (ImGui::Selectable(kPages[i], g_page == i, 0, ImVec2(0, 28 * u))) {
            g_page = i;
            if (i == P_RESUME) open_locked(false);
            if (i == P_STATES) g_refresh_slots = true;
        }
    }
    ImGui::EndChild();
    ImGui::SameLine();
    ImGui::BeginChild("page", ImVec2(0, -ImGui::GetFrameHeightWithSpacing()), ImGuiChildFlags_None);
    switch (g_page) {
    case P_RESUME:
        ImGui::TextWrapped("Pick a page on the left, or press F1 / Esc (Select + L3 or Start on a "
                           "controller) to go back to the game.");
        break;
    case P_STATES: page_states(u); break;
    case P_CONTROLS: page_controls(u); break;
    case P_BINDS: page_binds(u); break;
    case P_MANUAL: page_manual(u); break;
    case P_QUIT: page_quit(u); break;
    }
    ImGui::EndChild();
    ImGui::TextDisabled("%s", g_status.c_str());
    ImGui::End();
    ImGui::Render();
    ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
    ImGui::SetCurrentContext(prev);
}

void p_detach(void *) {
    ImGuiContext *prev = ImGui::GetCurrentContext();
    if (g_ctx) {
        ImGui::SetCurrentContext(g_ctx);
        for (SlotInfo &s : g_slots) if (s.tex) { glDeleteTextures(1, &s.tex); s.tex = 0; }
        if (g_gl_ready) ImGui_ImplOpenGL3_Shutdown();
        ImGui::DestroyContext(g_ctx);
        g_ctx = nullptr;
        g_gl_ready = false;
        g_font_px = 0;
    }
    ImGui::SetCurrentContext(prev == g_ctx ? nullptr : prev);
    std::lock_guard<std::mutex> lk(g_mu);
    g_refresh_slots = true;
}

// "Reset to defaults" posts action 3; run it on the main thread from is_open.
int p_is_open_wrapper(void *ctx) {
    {
        std::lock_guard<std::mutex> lk(g_mu);
        if (g_pending_action == 3) {
            g_pending_action = 0;
            psx_keybinds_reset_player(1);
            psx_keybinds_save();
            g_status = "Keyboard bindings reset to defaults.";
        }
    }
    return p_is_open(ctx);
}

const PsxMenuProvider kProvider = {
    PSX_MENU_ABI_VERSION, GM_PROVIDER_NAME, nullptr,
    p_attach, p_event, p_is_open_wrapper, p_set_open, p_draw, p_detach,
};

struct Register {
    Register() { psx_menu_set_provider(&kProvider); }
} g_register;

}  // namespace
