#!/usr/bin/env python3
"""Turn a pristine RustDesk source tree into "Santalvo Support".

Run once from the repo root on an untouched upstream tag:
    python3 branding/apply_branding.py
Every replacement must hit exactly the expected number of times, otherwise the
script stops - so after pulling a new upstream version you see at once what moved.

Needs: rsvg-convert, ImageMagick (convert). Icons come from branding/logo/*.svg.
"""
import os, re, struct, subprocess, sys, tempfile
from pathlib import Path

# ---------------------------------------------------------------- settings
APP_NAME      = "SantalvoSupport"          # internal: exe, service, config folder. Letters only - no spaces.
DISPLAY_NAME  = "Santalvo Support"         # what people see
LINUX_NAME    = APP_NAME.lower()           # santalvosupport (binary, service, package)
COMPANY       = "Santalvo Systems"
BUNDLE_ID     = "us.santalvo.support"
WEBSITE       = "https://santalvo.com"
PRIVACY       = "https://santalvo.com/privacy.html"
COPYRIGHT     = ("Copyright (C) 2026 Santalvo Systems. Based on RustDesk, "
                 "Copyright (C) Purslane Tech Pte. Ltd., AGPL-3.0")
BG            = "#15181E"                  # icon background (Android adaptive icon)

ROOT = Path.cwd()
BR = ROOT / "branding"
MARK = ROOT / ".santalvo-branded"
changed = []


def sub(path, old, new, count=1, regex=False):
    """Replace old->new in path; require exactly `count` hits (0 = at least one)."""
    p = ROOT / path
    s = p.read_text(encoding="utf-8")
    hits = len(re.findall(old, s)) if regex else s.count(old)
    if (count and hits != count) or (not count and hits == 0):
        sys.exit(f"STOP: {path}: expected {count or '>=1'} x {old!r}, found {hits}")
    s = re.sub(old, new, s) if regex else s.replace(old, new)
    p.write_text(s, encoding="utf-8")
    changed.append(str(path))


def run(*a):
    subprocess.run(a, check=True)


# ---------------------------------------------------------------- 1. core settings
def core():
    c = "libs/hbb_common/src/config.rs"
    sub(c, 'APP_NAME: RwLock<String> = RwLock::new("RustDesk".to_owned())',
           f'APP_NAME: RwLock<String> = RwLock::new("{APP_NAME}".to_owned())')
    # Server name and public key are NOT written into the source. The source holds the
    # placeholders below; each build job swaps in the GitHub secrets RENDEZVOUS_SERVER and
    # RS_PUB_KEY right after checkout (branding/inject_secrets.sh), so the public repo never
    # shows them. The workflow refuses to build if either secret is missing.
    sub(c, 'pub const RENDEZVOUS_SERVERS: &[&str] = &["rs-ny.rustdesk.com"];',
           'pub const RENDEZVOUS_SERVERS: &[&str] = &["@@RENDEZVOUS_SERVER@@"];')
    sub(c, re.escape('pub const RS_PUB_KEY: &str = "') + r'[A-Za-z0-9+/=]+";',
           'pub const RS_PUB_KEY: &str = "@@RS_PUB_KEY@@";', regex=True)
    # Translated text says "RustDesk" in many places: show the friendly name instead.
    sub("src/lang.rs", "                let app_name = crate::get_app_name();\n                if !app_name.contains(\"RustDesk\")",
        f"                let app_name = \"{DISPLAY_NAME}\".to_owned();\n                if !app_name.contains(\"RustDesk\")")
    # 2FA authenticator label
    sub("src/auth_2fa.rs", 'const ISSUER: &str = "RustDesk";', f'const ISSUER: &str = "{DISPLAY_NAME}";')


# ---------------------------------------------------------------- 2. desktop UI text
def flutter_ui():
    sub("flutter/lib/common.dart",
        "String getWindowName({WindowType? overrideType}) {\n  final name = bind.mainGetAppNameSync();",
        f"String getWindowName({{WindowType? overrideType}}) {{\n  final name = '{DISPLAY_NAME}';")
    sub("flutter/lib/main.dart", "              : bind.mainGetAppNameSync(),",
        f"              : '{DISPLAY_NAME}',")
    sub("flutter/lib/mobile/pages/home_page.dart", "return Text(bind.mainGetAppNameSync());",
        f"return Text('{DISPLAY_NAME}');")
    sub("flutter/lib/desktop/widgets/tabbar_widget.dart",
        '                            child: const Text(\n                              "RustDesk",',
        f'                            child: const Text(\n                              "{DISPLAY_NAME}",')
    s = "flutter/lib/desktop/pages/desktop_setting_page.dart"
    sub(s, "launchUrlString('https://rustdesk.com/privacy.html');", f"launchUrlString('{PRIVACY}');")
    sub(s, "launchUrlString('https://rustdesk.com');", f"launchUrlString('{WEBSITE}');")


# ---------------------------------------------------------------- 3. Windows
def windows():
    w = "src/platform/windows.rs"
    sub(w, 'reg add {subkey} /f /v DisplayName /t REG_SZ /d \\"{app_name}\\"',
           f'reg add {{subkey}} /f /v DisplayName /t REG_SZ /d \\"{DISPLAY_NAME}\\"')
    sub(w, 'reg add {subkey} /f /v Publisher /t REG_SZ /d \\"{app_name}\\"',
           f'reg add {{subkey}} /f /v Publisher /t REG_SZ /d \\"{COMPANY}\\"')
    sub(w, 'DisplayName= \\"{app_name} Service\\"', f'DisplayName= \\"{DISPLAY_NAME} Service\\"', count=2)
    r = "flutter/windows/runner/Runner.rc"
    sub(r, 'VALUE "CompanyName", "Purslane Tech Pte. Ltd." "\\0"', f'VALUE "CompanyName", "{COMPANY}" "\\0"')
    sub(r, 'VALUE "FileDescription", "RustDesk Remote Desktop" "\\0"', f'VALUE "FileDescription", "{DISPLAY_NAME}" "\\0"')
    sub(r, r'VALUE "LegalCopyright", "[^"]*" "\\0"', f'VALUE "LegalCopyright", "{COPYRIGHT}" "\\\\0"', regex=True)
    sub(r, 'VALUE "ProductName", "RustDesk" "\\0"', f'VALUE "ProductName", "{DISPLAY_NAME}" "\\0"')


# ---------------------------------------------------------------- 4. macOS
def macos():
    x = "flutter/macos/Runner/Configs/AppInfo.xcconfig"
    sub(x, "PRODUCT_NAME = RustDesk", f"PRODUCT_NAME = {APP_NAME}")
    sub(x, "PRODUCT_BUNDLE_IDENTIFIER = com.carriez.flutterHbb", f"PRODUCT_BUNDLE_IDENTIFIER = {BUNDLE_ID}")
    sub(x, r"PRODUCT_COPYRIGHT = .*", f"PRODUCT_COPYRIGHT = {COPYRIGHT}", regex=True)
    # Swift module name follows PRODUCT_NAME, so the storyboard must point at the new module
    sub("flutter/macos/Runner/Base.lproj/MainMenu.xib", 'customModule="RustDesk"', f'customModule="{APP_NAME}"', count=2)
    sub("flutter/macos/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme",
        'BuildableName = "RustDesk.app"', f'BuildableName = "{APP_NAME}.app"', count=0)
    sub("flutter/macos/Runner.xcodeproj/project.pbxproj", "RustDesk.app", f"{APP_NAME}.app", count=0)
    sub("build.py", "RustDesk.app", f"{APP_NAME}.app", count=0)


# ---------------------------------------------------------------- 5. Linux (.deb)
def linux():
    sub("flutter/linux/CMakeLists.txt", 'set(BINARY_NAME "rustdesk")', f'set(BINARY_NAME "{LINUX_NAME}")')
    b = "build.py"
    sub(b, "tmpdeb/usr/share/rustdesk", f"tmpdeb/usr/share/{LINUX_NAME}", count=0)
    sub(b, f"tmpdeb/usr/share/{LINUX_NAME}/rustdesk'", f"tmpdeb/usr/share/{LINUX_NAME}/{LINUX_NAME}'", count=0)
    sub(b, "tmpdeb/usr/bin/rustdesk", f"tmpdeb/usr/bin/{LINUX_NAME}", count=0)
    sub(b, "apps/rustdesk.png", f"apps/{LINUX_NAME}.png", count=0)
    sub(b, "apps/rustdesk.svg", f"apps/{LINUX_NAME}.svg", count=0)
    sub(b, "tmpdeb/usr/share/applications/rustdesk.desktop", f"tmpdeb/usr/share/applications/{LINUX_NAME}.desktop", count=0)
    sub(b, "tmpdeb/usr/share/applications/rustdesk-link.desktop", f"tmpdeb/usr/share/applications/{LINUX_NAME}-link.desktop", count=0)
    sub(b, f"cp ../res/rustdesk.service tmpdeb/usr/share/{LINUX_NAME}/files/systemd/'",
           f"cp ../res/rustdesk.service tmpdeb/usr/share/{LINUX_NAME}/files/systemd/{LINUX_NAME}.service'", count=0)
    sub(b, '"""Package: rustdesk', f'"""Package: {LINUX_NAME}')
    sub(b, "Maintainer: rustdesk <info@rustdesk.com>", f"Maintainer: {COMPANY} <support@santalvo.com>")
    sub(b, "Homepage: https://rustdesk.com", f"Homepage: {WEBSITE}")
    # package scripts, service and menu entries: the command is now `santalvosupport`
    for f in ["res/DEBIAN/preinst", "res/DEBIAN/prerm", "res/DEBIAN/postrm", "res/DEBIAN/postinst",
              "res/rustdesk.service", "res/rustdesk.desktop", "res/rustdesk-link.desktop"]:
        p = ROOT / f
        s0 = p.read_text(encoding="utf-8")
        s = re.sub(r"(?<![\w/-])rustdesk(?![\w-])", LINUX_NAME, s0)
        # path fragments such as /usr/share/rustdesk/rustdesk
        s = s.replace("/rustdesk", f"/{LINUX_NAME}")
        if s == s0:
            sys.exit(f"STOP: {f}: no rustdesk names found")
        changed.append(f)
        s = s.replace(f"x-scheme-handler/{LINUX_NAME}", "x-scheme-handler/rustdesk")
        p.write_text(s, encoding="utf-8")
    for f in ["res/rustdesk.desktop", "res/rustdesk-link.desktop"]:
        sub(f, "Name=RustDesk", f"Name={DISPLAY_NAME}")


# ---------------------------------------------------------------- 6. Android
def android():
    sub("flutter/android/app/build.gradle", 'applicationId "com.carriez.flutter_hbb"', f'applicationId "{BUNDLE_ID}"')
    m = "flutter/android/app/src/main/AndroidManifest.xml"
    sub(m, 'android:label="RustDesk"', f'android:label="{DISPLAY_NAME}"')
    sub(m, 'android:label="RustDesk Input"', f'android:label="{DISPLAY_NAME} Input"')
    s = "flutter/android/app/src/main/res/values/strings.xml"
    sub(s, '<string name="app_name">RustDesk</string>', f'<string name="app_name">{DISPLAY_NAME}</string>')
    sub(s, "RustDesk", DISPLAY_NAME, count=0)
    sub("flutter/android/app/src/main/res/values/ic_launcher_background.xml", "#ffffff", BG)


# ---------------------------------------------------------------- 7. icons
def svg_to_png(svg, png, size):
    run("rsvg-convert", "-w", str(size), "-h", str(size), "-o", str(png), str(svg))


def write_icns(out, pngs):
    """pngs: {size: path}. Minimal PNG-based .icns."""
    types = {16: b"icp4", 32: b"icp5", 64: b"icp6", 128: b"ic07", 256: b"ic08", 512: b"ic09", 1024: b"ic10"}
    body = b""
    for size, t in types.items():
        data = Path(pngs[size]).read_bytes()
        body += t + struct.pack(">I", len(data) + 8) + data
    Path(out).write_bytes(b"icns" + struct.pack(">I", len(body) + 8) + body)


def icons():
    full = BR / "logo" / "icon.svg"            # dark rounded square, white S, teal dot
    glyph = BR / "logo" / "glyph-white.svg"    # S + dot only, white, transparent background
    glyph_k = BR / "logo" / "glyph-black.svg"  # S + dot only, black (template images)
    fg = BR / "logo" / "android-foreground.svg"
    t = Path(tempfile.mkdtemp())
    sizes = [16, 24, 32, 48, 64, 128, 256, 512, 1024]
    for n in sizes:
        svg_to_png(full, t / f"{n}.png", n)

    def cp(src, dst):
        (ROOT / dst).write_bytes(Path(src).read_bytes()); changed.append(dst)

    def ico(dst, ns):
        run("convert", *[str(t / f"{n}.png") for n in ns], str(ROOT / dst)); changed.append(dst)

    # shared / Windows
    cp(t / "1024.png", "res/icon.png")
    cp(t / "1024.png", "res/mac-icon.png")
    cp(t / "32.png", "res/32x32.png")
    cp(t / "64.png", "res/64x64.png")
    cp(t / "128.png", "res/128x128.png")
    cp(t / "256.png", "res/128x128@2x.png")
    ico("res/icon.ico", [16, 24, 32, 48, 64, 128, 256])
    ico("res/tray-icon.ico", [16, 24, 32, 48])
    ico("flutter/windows/runner/resources/app_icon.ico", [16, 24, 32, 48, 64, 128, 256])
    for f in ["res/scalable.svg", "res/logo.svg", "res/logo-header.svg", "flutter/assets/icon.svg"]:
        cp(full, f)
    # macOS app + menu-bar (template) icons
    write_icns(ROOT / "flutter/macos/Runner/AppIcon.icns", {n: t / f"{n}.png" for n in [16, 32, 64, 128, 256, 512, 1024]})
    changed.append("flutter/macos/Runner/AppIcon.icns")
    svg_to_png(glyph, ROOT / "res/mac-tray-dark-x2.png", 60)
    svg_to_png(glyph_k, ROOT / "res/mac-tray-light-x2.png", 48)
    # Android launcher, adaptive foreground, notification icon
    dens = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    for d, k in dens.items():
        base = f"flutter/android/app/src/main/res/mipmap-{d}/"
        svg_to_png(full, ROOT / (base + "ic_launcher.png"), int(48 * k))
        svg_to_png(full, ROOT / (base + "ic_launcher_round.png"), int(48 * k))
        svg_to_png(fg, ROOT / (base + "ic_launcher_foreground.png"), int(108 * k))
        svg_to_png(glyph, ROOT / (base + "ic_stat_logo.png"), int(24 * k))
    svg_to_png(full, ROOT / "fastlane/metadata/android/en-US/images/icon.png", 512)


def main():
    if MARK.exists():
        sys.exit("Already branded (.santalvo-branded exists). Start from a clean upstream checkout.")
    for need in ("rsvg-convert", "convert"):
        if subprocess.run(["which", need], capture_output=True).returncode:
            sys.exit(f"Missing tool: {need}")
    core(); flutter_ui(); windows(); macos(); linux(); android(); icons()
    MARK.write_text(f"Branded as {DISPLAY_NAME} ({APP_NAME})\n")
    print(f"Branded {len(set(changed))} files.")


if __name__ == "__main__":
    main()
