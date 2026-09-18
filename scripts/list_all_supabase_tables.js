const ACCESS_TOKEN = process.env.SUPABASE_ACCESS_TOKEN || '';
const PROJECT_REF = process.env.SUPABASE_PROJECT_REF || 'xeckbeavsvyoporldjzm';

async function listAll() {
  const res = await fetch(`https://api.supabase.com/v1/projects/${PROJECT_REF}/database/query`, {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${ACCESS_TOKEN}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      query: `
        SELECT 
          table_name, 
          (SELECT count(*) FROM information_schema.columns WHERE table_name = t.table_name AND table_schema = 'public') as column_count
        FROM information_schema.tables t
        WHERE table_schema = 'public'
        ORDER BY table_name;
      `
    })
  });

  const tables = await res.json();
  console.log('=' .repeat(60));
  console.log(' ALL PUBLIC TABLES PRESENT IN SUPABASE DATABASE:');
  console.log('=' .repeat(60));
  if (Array.isArray(tables)) {
    tables.forEach(t => {
      console.log(` [+] Table: ${t.table_name} (${t.column_count} columns)`);
    });
  } else {
    console.log(tables);
  }
  console.log('=' .repeat(60));
}

listAll().catch(console.error);
