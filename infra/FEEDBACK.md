# Visitor feedback → private Sheet + email notification

## How visitors submit opinions

- Public page: `https://based-on-our-reporting.com/about`, under the introduction.
- The **의견 보내기** accordion expands to one textarea and a **전송하기** button.
- POST `/api/feedback` validates 2–3,000 characters, a unique retry ID and a honeypot.
- A successful POST appends immediately to the existing private Google spreadsheet,
  tab **의견 보내기**, columns **접수 ID / 접수 시각(KST) / 의견 내용 / 알림 발송 시각 / 처리 메모**.
- The sheet is private; its address and OAuth credentials are never exposed to the page.
- A global Firestore quota limits processing to 150 new submissions/day. Duplicate
  client retries with the same ID are deduplicated.
- If Sheets cannot be reached, Firestore retains a pending copy. The existing 30-minute
  archive run reconciles pending submissions by ID without overwriting email status or notes.
  The visitor receives a retryable error until the destination write is confirmed.

## Email notifications (one-time owner authorization)

Google Apps Script `onEdit` triggers do **not** run for changes made via the
Google Sheets API. Instead the provided script checks the private opinion tab
once an hour and sends one digest email for any new rows; it marks the
**알림 발송 시각(KST)** column only after sending.

1. Open the existing [data archive spreadsheet](https://docs.google.com/spreadsheets/d/1pLRILhu02VX1_KYDgEaRjOeL4WgBP_1Wmh-mm-iFcaY/edit#gid=209).
2. Select **확장 프로그램 → Apps Script**.
3. Paste all of [feedback-alerts.gs](./feedback-alerts.gs) into the editor's
   `Code.gs`, replacing example starter code. Save.
4. Optionally fill `RECIPIENT_EMAIL` with your own email address. Leave empty
   to send to the Google account that installs the trigger.
5. Choose **installOpinionEmailAlerts** from the function menu and click **실행**.
   Accept Google's requested Sheets, trigger and mail scopes.
6. Confirm under Apps Script **트리거** that `checkOpinionMessages` runs
   every hour. For a test, create a real feedback submission through
   the public page and confirm the new row and a notification email.

The Assistant cannot approve personal email-sending scopes on the owner's behalf.
If you already installed the five-minute version, replace Code.gs with the new script\nand run **installOpinionEmailAlerts** again. It deletes the existing opinion\ntrigger and creates an hourly one. The previously granted OAuth scopes can be reused.\nThe site works without notifications.
To stop emails, delete that time-driven trigger in Apps Script.
