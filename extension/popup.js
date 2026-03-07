document.getElementById('save').onclick = async () => {
  const key = document.getElementById('apiKey').value;
  await chrome.storage.local.set({ apiKey: key });
  alert('API Key saved!');
};

document.getElementById('upload').onclick = async () => {
  const file = document.getElementById('file').files[0];
  if (!file) { alert('Select a file!'); return; }
  
  const { apiKey } = await chrome.storage.local.get('apiKey');
  if (!apiKey) { alert('Save API key first!'); return; }
  
  const formData = new FormData();
  formData.append('file', file);
  
  document.getElementById('result').innerText = 'Uploading...';
  
  try {
    const resp = await fetch('https://bottube.ai/api/videos', {
      method: 'POST',
      headers: { 'X-API-Key': apiKey },
      body: formData
    });
    const data = await resp.json();
    document.getElementById('result').innerText = 'Uploaded! ' + (data.id || '');
  } catch (e) {
    document.getElementById('result').innerText = 'Error: ' + e.message;
  }
};
