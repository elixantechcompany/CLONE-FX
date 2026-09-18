const fs = require('fs');
const path = require('path');

const ACCESS_TOKEN = process.env.SUPABASE_ACCESS_TOKEN || '';
const PROJECT_REF = process.env.SUPABASE_PROJECT_REF || 'xeckbeavsvyoporldjzm';
const SCHEMA_PATH = path.join(__dirname, '..', 'signals-web', 'supabase', 'schema.sql');

async function executeSql() {
  console.log('=' .repeat(60));
  console.log(' SUPABASE MANAGEMENT API - DIRECT SQL EXECUTION');
  console.log('=' .repeat(60));

  const sqlContent = fs.readFileSync(SCHEMA_PATH, 'utf-8');
  console.log(`[+] Read schema.sql (${sqlContent.length} bytes)`);

  const url = `https://api.supabase.com/v1/projects/${PROJECT_REF}/database/query`;
  console.log(`[*] Sending SQL execution request to: ${url}`);

  const response = await fetch(url, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${ACCESS_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ query: sqlContent }),
  });

  const status = response.status;
  const data = await response.text();

  console.log(`[+] Response Status: ${status}`);
  console.log(`[+] Response Data:`, data);

  if (status === 200 || status === 201) {
    console.log('\n[✓] SQL MIGRATION EXECUTED SUCCESSFULLY VIA MANAGEMENT API!');
  } else {
    console.error('\n[!] Execution failed with status:', status);
  }
}

executeSql().catch(err => {
  console.error('Fatal error:', err);
  process.exit(1);
});
