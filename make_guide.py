"""
make_guide.py — Generates TwitchWatcher_Setup_Guide.pdf

This is the editable source for the bundled setup guide. Edit the content
below and run `python make_guide.py` to regenerate the PDF, then rebuild the
app with build.bat so the new guide gets bundled into the exe.
"""

from reportlab.lib.pagesizes import letter
from reportlab.lib.units import inch
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, HRFlowable, ListFlowable, ListItem,
)

PURPLE = colors.HexColor("#772CE8")   # Twitch-ish purple
GRAY   = colors.HexColor("#666666")
WARN_BG   = colors.HexColor("#FFF4E5")
WARN_TEXT = colors.HexColor("#B3541E")

styles = getSampleStyleSheet()

title_style = ParagraphStyle("TitleX", parent=styles["Title"],
                             textColor=PURPLE, fontSize=26, spaceAfter=2, alignment=1)
subtitle_style = ParagraphStyle("Subtitle", parent=styles["Normal"],
                                textColor=GRAY, fontSize=11, alignment=1, spaceAfter=10)
intro_style = ParagraphStyle("Intro", parent=styles["Normal"], fontSize=10.5,
                             leading=15, spaceAfter=8)
heading_style = ParagraphStyle("HeadingX", parent=styles["Heading2"],
                               textColor=PURPLE, fontSize=14, spaceBefore=14, spaceAfter=4)
body_style = ParagraphStyle("BodyX", parent=styles["Normal"], fontSize=10.5, leading=15)
bullet_style = ParagraphStyle("BulletX", parent=body_style, leftIndent=14)
warn_style = ParagraphStyle("Warn", parent=body_style, textColor=WARN_TEXT,
                            backColor=WARN_BG, borderColor=WARN_TEXT, borderWidth=0.5,
                            borderPadding=8, spaceBefore=6, spaceAfter=6, leading=15)
faq_q_style = ParagraphStyle("FaqQ", parent=body_style, fontName="Helvetica-Bold",
                             spaceBefore=8, spaceAfter=2)


def bullets(items):
    return ListFlowable(
        [ListItem(Paragraph(t, bullet_style), leftIndent=18, value="•") for t in items],
        bulletType="bullet", start="•", leftIndent=10,
    )


def build(path="TwitchWatcher_Setup_Guide.pdf"):
    doc = SimpleDocTemplate(path, pagesize=letter,
                            topMargin=0.8 * inch, bottomMargin=0.8 * inch,
                            leftMargin=0.9 * inch, rightMargin=0.9 * inch,
                            title="TwitchWatcher Setup Guide")
    s = []
    s.append(Paragraph("TwitchWatcher", title_style))
    s.append(Paragraph("Setup Guide — Getting Your Twitch API Credentials", subtitle_style))
    s.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#DDDDDD"), spaceAfter=10))

    s.append(Paragraph(
        "Before using TwitchWatcher you need a free Twitch Developer account and a "
        "registered app. This sounds scarier than it is — it takes about 5 minutes and "
        "you only do it once.", intro_style))

    s.append(Paragraph("Step 1 — Log Into the Twitch Developer Console", heading_style))
    s.append(bullets([
        "Go to <b>https://dev.twitch.tv/console</b>",
        "Click <b>Log In with Twitch</b> in the top right corner",
        "Sign in with your normal Twitch account",
    ]))

    s.append(Paragraph("Step 2 — Register a New App", heading_style))
    s.append(bullets([
        "Once logged in, click <b>Applications</b> in the left sidebar",
        "Click the <b>Register Your Application</b> button",
    ]))
    s.append(Spacer(1, 4))
    s.append(Paragraph("Fill in the form:", body_style))
    s.append(bullets([
        "<b>Name:</b> Pick any name that does <b>not</b> contain the word "
        "&quot;Twitch&quot; — their console rejects those. Use your username or a "
        "nickname (e.g. <i>FrogWatch</i>). This is just an internal label and does not "
        "affect how TwitchWatcher works.",
        "<b>OAuth Redirect URLs:</b> Type <font face='Courier'>http://localhost</font> and click Add",
        "<b>Category:</b> Select Application Integration",
        "<b>Client Type:</b> Select Confidential",
        "Check the <b>I'm not a robot</b> box",
        "Click <b>Create</b>",
    ]))

    s.append(Paragraph("Step 3 — Get Your Client ID", heading_style))
    s.append(bullets([
        "You'll be taken back to the Applications list",
        "Click <b>Manage</b> next to the app you just created",
        "You'll see a <b>Client ID</b> — a long string of letters and numbers",
        "Copy it and keep it handy",
    ]))

    s.append(Paragraph("Step 4 — Generate Your Client Secret", heading_style))
    s.append(bullets([
        "On the same page, scroll down and click <b>New Secret</b>",
        "A popup will warn you — click <b>OK</b>",
        "Your <b>Client Secret</b> will appear — <b>copy it immediately</b>",
    ]))
    s.append(Paragraph(
        "&#9632; Twitch only shows the Client Secret ONCE. If you close the page without "
        "copying it, you will need to generate a new one.", warn_style))

    s.append(Paragraph("Step 5 — Enter Your Credentials in TwitchWatcher", heading_style))
    s.append(bullets([
        "Open TwitchWatcher",
        "Click the <b>Settings</b> tab",
        "Paste your <b>Client ID</b> into the Client ID field",
        "Paste your <b>Client Secret</b> into the Client Secret field",
        "Click <b>Save Settings</b>",
    ]))
    s.append(Paragraph(
        "Your Client Secret is stored securely in <b>Windows Credential Manager</b> — the "
        "same encrypted vault your browser uses for saved passwords. It is never written "
        "to a file on your computer.", body_style))

    s.append(Paragraph("Step 6 — Add Your First Streamer", heading_style))
    s.append(bullets([
        "Click the <b>Streamers</b> tab",
        "Type a Twitch username in the Username field",
        "Optionally assign a <b>Group</b> (e.g. &quot;Friends&quot;, &quot;Gamers&quot;, "
        "&quot;Drops&quot;) to keep things organised",
        "Tick <b>Drops Only</b> if you only want alerts when that streamer has drops in their title",
        "Click <b>Add</b> or press Enter",
    ]))

    s.append(Paragraph("Step 7 — Start Watching", heading_style))
    s.append(bullets([
        "Click <b>Start Watching</b> at the bottom of the app",
        "TwitchWatcher will check Twitch every 5 minutes (configurable in Settings)",
        "When a streamer goes live you'll get a Windows notification and their channel "
        "opens in your browser",
    ]))

    s.append(Paragraph("Optional — Autostart", heading_style))
    s.append(Paragraph("If you want TwitchWatcher to start watching automatically every "
                       "time you open it:", body_style))
    s.append(bullets([
        "Go to <b>Settings</b>",
        "Tick <b>Start watching automatically when app opens</b>",
        "Click <b>Save Settings</b>",
    ]))

    # ----- FAQ -----
    s.append(Paragraph("FAQ", heading_style))

    s.append(Paragraph("What should I name my app on the Twitch Developer Console?", faq_q_style))
    s.append(Paragraph(
        "Twitch does not allow the word &quot;Twitch&quot; in the app name, so "
        "&quot;TwitchWatcher&quot; will be rejected. Use anything else — your username "
        "or a nickname like <i>FrogWatch</i>. It is just an internal label and does not "
        "affect how TwitchWatcher works.", body_style))

    s.append(Paragraph("Do I need to build a website or host anything?", faq_q_style))
    s.append(Paragraph(
        "No. The <font face='Courier'>http://localhost</font> redirect URL is just a "
        "required placeholder — nothing actually runs there. TwitchWatcher talks to "
        "Twitch's API directly from your PC.", body_style))

    # ----- Troubleshooting -----
    s.append(Paragraph("Troubleshooting", heading_style))
    for q, a in [
        ("&quot;Auth error: 403&quot;",
         "Your Client ID or Secret is wrong. Double-check you copied them correctly with "
         "no extra spaces. Go to Settings, re-enter both, and save again."),
        ("&quot;Auth error: 401&quot;",
         "Your token expired or your Secret was regenerated on the Twitch side. Go to "
         "dev.twitch.tv, generate a new Secret, paste it into Settings, and save."),
        ("Windows blocked the app / said it's a virus",
         "TwitchWatcher is not signed with a paid developer certificate, so Windows "
         "Defender may flag it as unknown publisher. This is normal for indie tools. "
         "Click <b>More info</b> &#8594; <b>Run anyway</b> to proceed. TwitchWatcher only "
         "connects to Twitch's official API."),
        ("Notifications aren't appearing",
         "Go to Windows Settings &#8594; System &#8594; Notifications and make sure "
         "notifications are enabled."),
        ("I moved the app and lost my settings",
         "Your settings are saved in <font face='Courier'>twitch_watcher_config.json</font> "
         "in the same folder as the app. Move that file to the new folder too. Your Client "
         "Secret is stored in Windows Credential Manager and carries over automatically."),
    ]:
        s.append(Paragraph(q, faq_q_style))
        s.append(Paragraph(a, body_style))

    # ----- Privacy -----
    s.append(Paragraph("Privacy &amp; Security", heading_style))
    s.append(bullets([
        "TwitchWatcher only communicates with <font face='Courier'>https://id.twitch.tv</font> "
        "and <font face='Courier'>https://api.twitch.tv</font>",
        "Your credentials are stored locally on your machine only",
        "No data is collected, no accounts are created, nothing is sent to any third party",
        "Source code is available on GitHub for anyone to review",
    ]))

    doc.build(s)
    print(f"Wrote {path}")


if __name__ == "__main__":
    build()
