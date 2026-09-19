import { ConfluenceSignal } from './types';

const TELEGRAM_BOT_TOKEN = process.env.TELEGRAM_BOT_TOKEN || '';
const TELEGRAM_CHAT_ID = process.env.TELEGRAM_CHAT_ID || '';

/**
 * Sends formatted Markdown trade alert to Telegram chat
 */
export async function sendTelegramSignalAlert(signal: ConfluenceSignal): Promise<boolean> {
  if (!TELEGRAM_BOT_TOKEN || !TELEGRAM_CHAT_ID) {
    console.log('[Telegram] Skipping alert: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not configured.');
    return false;
  }

  const isLong = signal.direction === 'LONG';
  const dirEmoji = isLong ? '🟢 BUY / LONG' : '🔴 SELL / SHORT';
  const confidenceBadge = signal.confluenceScore === '3/3' ? '⭐ 3/3 PROP FIRM READY' : '⚠️ 2/3 CAUTION';

  const message = `
🚨 *NEW PROP FIRM SETUP CONFIRMED*
━━━━━━━━━━━━━━━━━━━━━━━━━━
*Symbol:* \`${signal.symbol}\`
*Direction:* *${dirEmoji}*
*Confidence:* *${confidenceBadge}*

🎯 *Entry:* \`${signal.entryPrice.toFixed(2)}\`
🛑 *Stop Loss:* \`${signal.stopLoss.toFixed(2)}\` (\`${signal.slDistance.toFixed(2)}\` pts / 1.5x 30M ATR)
🏆 *Take Profit 1:* \`${signal.takeProfit1.toFixed(2)}\` (\`${signal.tpDistance.toFixed(2)}\` pts / 1:2.0 R:R)
${signal.takeProfit2 ? `🚀 *Take Profit 2:* \`${signal.takeProfit2.toFixed(2)}\` (1:3.2 R:R)\n` : ''}*Risk / Reward:* *1:${signal.riskReward.toFixed(2)}*

📊 *3-Timeframe Confluence Stack:*
• *D1/4H Bias:* ${signal.timeframeStack?.['4H'] || signal.htfConfluence?.dailyBias || 'Aligned'}
• *1H Setup:* ${signal.timeframeStack?.['1H'] || signal.htfConfluence?.h4Structure || 'Aligned'}
• *1H Trigger:* ${signal.timeframeStack?.['30M'] || signal.htfConfluence?.h1Trigger || 'Triggered'}

🛡️ *Rules Checklist:*
${signal.confluences.map((c) => `• ${c}`).join('\n')}

━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️ *Prop Guardrail:* Manual review required. Max 2-3 trades/day limit.
`.trim();

  try {
    const url = `https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage`;
    const res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        chat_id: TELEGRAM_CHAT_ID,
        text: message,
        parse_mode: 'Markdown',
      }),
    });

    const data = await res.json();
    return data.ok === true;
  } catch (err) {
    console.error('[Telegram] Failed to send alert:', err);
    return false;
  }
}
