/**
 * Install once in the Apps Script editor of:
 * 취재를 종합하면 | 일별 데이터 아카이브
 *
 * Run installOpinionEmailAlerts() once and grant MailApp/Sheets/trigger permissions.
 * Unlike onEdit/onChange, a time-driven trigger works for API-written rows.
 *
 * For explicit routing, put your address in RECIPIENT_EMAIL. If blank,
 * the email address of the trigger creator is used.
 */
const OPINION_SHEET = '의견 보내기';
const RECIPIENT_EMAIL = '';

function installOpinionEmailAlerts() {
  const address = RECIPIENT_EMAIL || Session.getEffectiveUser().getEmail();
  if (!address || !address.includes('@')) {
    throw new Error('RECIPIENT_EMAIL 상수에 알림 받을 이메일 주소를 입력해주세요.');
  }
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss || !ss.getSheetByName(OPINION_SHEET)) {
    throw new Error('스프레드시트에서 의견 보내기 시트를 찾지 못했습니다.');
  }
  const existing = ScriptApp.getProjectTriggers();
  for (const trigger of existing) {
    if (trigger.getHandlerFunction() === 'checkOpinionMessages') {
      ScriptApp.deleteTrigger(trigger);
    }
  }
  ScriptApp.newTrigger('checkOpinionMessages').timeBased().everyHours(1).create();
  console.log('새 의견 이메일 알림 설정됨: ' + address);
}

function checkOpinionMessages() {
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) return;
  try {
    const sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(OPINION_SHEET);
    if (!sheet) throw new Error('의견 보내기 시트를 찾을 수 없습니다.');
    const last = sheet.getLastRow();
    if (last <= 1) return;
    const rows = sheet.getRange(2, 1, last - 1, 4).getValues();
    const pending = [];
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i];
      if (row[0] && row[2] && !row[3]) pending.push({row: i + 2, when: row[1], opinion: String(row[2])});
    }
    if (!pending.length) return;
    const destination = RECIPIENT_EMAIL || Session.getEffectiveUser().getEmail();
    if (!destination) throw new Error('이메일 주소를 확인할 수 없습니다. RECIPIENT_EMAIL을 지정해주세요.');
    const visible = pending.slice(0, 10);
    const body = [
      '‘취재를 종합하면’ 사이트에 새로운 의견 ' + pending.length + '건이 접수됐습니다.',
      '',
      ...visible.flatMap((x, i) => [
        '[' + (i + 1) + '] ' + String(x.when),
        x.opinion.slice(0, 1000),
        ''
      ]),
      ...(pending.length > visible.length ? ['그 밖의 ' + (pending.length - visible.length) + '건은 스프레드시트에서 확인해주세요.', ''] : []),
      '모든 의견 확인: https://docs.google.com/spreadsheets/d/1pLRILhu02VX1_KYDgEaRjOeL4WgBP_1Wmh-mm-iFcaY/edit#gid=209'
    ].join('\n');
    // Mark as sent only after MailApp confirms the send call succeeded.
    MailApp.sendEmail({to: destination, subject: '[취재를 종합하면] 새로운 의견 ' + pending.length + '건', body});
    const timestamp = Utilities.formatDate(new Date(), 'Asia/Seoul', 'yyyy-MM-dd HH:mm:ss');
    for (const row of pending) sheet.getRange(row.row, 4).setValue(timestamp);
  } finally {
    lock.releaseLock();
  }
}
