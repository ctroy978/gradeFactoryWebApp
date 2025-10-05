const jobsTableContainer = document.getElementById('jobs-table-container');
const jobDetailPanel = document.getElementById('job-detail-panel');
const jobDetailTarget = document.getElementById('job-detail');
const closeDetailButton = document.getElementById('close-detail');
const refreshJobsButton = document.getElementById('refresh-jobs');

let pinValue = localStorage.getItem('gradefactoryPin');
if (pinValue === null || pinValue === '') {
  pinValue = null;
}

function buildHeaders(includePin) {
  const headers = {};
  if (includePin && pinValue) {
    headers['X-GradeFactory-Pin'] = pinValue;
  }
  return headers;
}

async function fetchWithPin(url, options = {}) {
  const attempt = async (withPin) => {
    const headers = { ...(options.headers || {}), ...buildHeaders(withPin) };
    return fetch(url, { ...options, headers });
  };

  let response = await attempt(Boolean(pinValue));
  if (response.status !== 401) {
    return response;
  }

  const entered = window.prompt('Enter the access PIN to continue:');
  if (!entered) {
    throw new Error('PIN required to continue');
  }
  pinValue = entered.trim();
  localStorage.setItem('gradefactoryPin', pinValue);

  response = await attempt(true);
  if (response.status === 401) {
    localStorage.removeItem('gradefactoryPin');
    pinValue = null;
    throw new Error('Invalid PIN');
  }
  return response;
}

async function submitForm(endpoint, formData) {
  try {
    const response = await fetchWithPin(endpoint, {
      method: 'POST',
      body: formData,
    });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const reason = payload.detail || response.statusText;
      throw new Error(reason);
    }
    const snapshot = await response.json();
    await loadJobs();
    await showJobDetail(snapshot['id']);
  } catch (error) {
    alert(`Job failed: ${error.message}`);
  }
}

function bindForm(formId, prepare) {
  const form = document.getElementById(formId);
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const submitter = event.submitter;
    if (submitter) {
      submitter.disabled = true;
    }
    try {
      const data = new FormData();
      await prepare(data);
    } finally {
      if (submitter) {
        submitter.disabled = false;
      }
    }
  });
}

bindForm('full-form', async (data) => {
  const rawInput = document.getElementById('full-raw');
  const rubricInput = document.getElementById('full-rubric');
  if (!rawInput.files.length || !rubricInput.files.length) {
    alert('Upload at least one raw essay and a rubric.');
    return;
  }
  const nameFlag = document.getElementById('full-name-flag').checked;
  data.append('name_flag', String(nameFlag));
  for (const file of rawInput.files) {
    data.append('raw_files', file);
  }
  data.append('rubric', rubricInput.files[0]);
  await submitForm('/jobs/full', data);
});

bindForm('process-form', async (data) => {
  const rawInput = document.getElementById('process-raw');
  if (!rawInput.files.length) {
    alert('Upload at least one raw essay.');
    return;
  }
  const nameFlag = document.getElementById('process-name-flag').checked;
  data.append('name_flag', String(nameFlag));
  for (const file of rawInput.files) {
    data.append('raw_files', file);
  }
  await submitForm('/jobs/process', data);
});

bindForm('grade-form', async (data) => {
  const processedInput = document.getElementById('grade-processed');
  const rubricInput = document.getElementById('grade-rubric');
  if (!processedInput.files.length || !rubricInput.files.length) {
    alert('Upload processed essays and a rubric.');
    return;
  }
  for (const file of processedInput.files) {
    data.append('processed_files', file);
  }
  data.append('rubric', rubricInput.files[0]);
  await submitForm('/jobs/grade', data);
});

async function loadJobs() {
  try {
    const response = await fetchWithPin('/jobs');
    if (!response.ok) {
      throw new Error('Unable to fetch jobs');
    }
    const jobs = await response.json();
    renderJobs(jobs.filter(Boolean));
  } catch (error) {
    jobsTableContainer.innerHTML = `<p class="error">${error.message}</p>`;
  }
}

function renderJobs(jobs) {
  if (!jobs.length) {
    jobsTableContainer.innerHTML = '<p>No jobs yet. Submit one above.</p>';
    return;
  }

  const table = document.createElement('table');
  table.innerHTML = '<thead><tr><th>ID</th><th>Type</th><th>Status</th><th>Updated</th><th></th></tr></thead>';
  const tbody = document.createElement('tbody');
  const template = document.getElementById('job-row-template');

  jobs
    .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at))
    .forEach((job) => {
      const row = template.content.cloneNode(true);
      row.querySelector('.job-id').textContent = job.id;
      row.querySelector('.job-type').textContent = job.type;
      row.querySelector('.job-status').textContent = job.status;
      row.querySelector('.job-updated').textContent = new Date(job.updated_at).toLocaleString();
      row.querySelector('.view-job').addEventListener('click', () => showJobDetail(job.id));
      row.querySelector('.delete-job').addEventListener('click', () => deleteJob(job.id));
      tbody.appendChild(row);
    });

  table.appendChild(tbody);
  jobsTableContainer.innerHTML = '';
  jobsTableContainer.appendChild(table);
}

async function showJobDetail(jobId) {
  try {
    const response = await fetchWithPin(`/jobs/${jobId}`);
    if (!response.ok) {
      throw new Error('Unable to fetch job detail');
    }
    const job = await response.json();
    renderJobDetail(job);
  } catch (error) {
    alert(error.message);
  }
}

function renderJobDetail(job) {
  jobDetailTarget.dataset.jobId = job.id;
  jobDetailTarget.innerHTML = '';
  const info = document.createElement('div');
  info.innerHTML = `
    <p><strong>ID:</strong> ${job.id}</p>
    <p><strong>Type:</strong> ${job.type}</p>
    <p><strong>Status:</strong> ${job.status}</p>
    <p><strong>Created:</strong> ${new Date(job.created_at).toLocaleString()}</p>
    <p><strong>Updated:</strong> ${new Date(job.updated_at).toLocaleString()}</p>
    ${job.error ? `<p class="error"><strong>Error:</strong> ${job.error}</p>` : ''}
  `;
  jobDetailTarget.appendChild(info);

  if (job.stages) {
    job.stages.forEach((stage) => {
      const section = document.createElement('section');
      section.innerHTML = `
        <h3>${stage.name}</h3>
        <p>Status: ${stage.status}</p>
        ${stage.stdout ? `<details><summary>Stdout</summary><pre>${stage.stdout}</pre></details>` : ''}
        ${stage.stderr ? `<details><summary>Stderr</summary><pre>${stage.stderr}</pre></details>` : ''}
      `;
      if (stage.output_files && stage.output_files.length) {
        const list = document.createElement('div');
        list.classList.add('artifact-list');
        list.innerHTML = '<strong>Artifacts:</strong>';
        stage.output_files.forEach((artifact) => {
          const link = document.createElement('a');
          link.href = `/jobs/${job.id}/artifacts/${artifact}`;
          link.textContent = artifact;
          link.target = '_blank';
          list.appendChild(link);
        });
        section.appendChild(list);
      }
      jobDetailTarget.appendChild(section);
    });
  }

  jobDetailPanel.hidden = false;
}

async function deleteJob(jobId) {
  const confirmed = window.confirm('Delete this job and all generated artifacts?');
  if (!confirmed) {
    return;
  }
  try {
    const response = await fetchWithPin(`/jobs/${jobId}`, { method: 'DELETE' });
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      const reason = payload.detail || response.statusText;
      throw new Error(reason);
    }
    if (jobDetailTarget.dataset.jobId && jobDetailTarget.dataset.jobId === jobId) {
      jobDetailTarget.dataset.jobId = '';
      jobDetailPanel.hidden = true;
      jobDetailTarget.innerHTML = '';
    }
    await loadJobs();
  } catch (error) {
    alert(`Unable to delete job: ${error.message}`);
  }
}

closeDetailButton.addEventListener('click', () => {
  jobDetailTarget.dataset.jobId = '';
  jobDetailPanel.hidden = true;
  jobDetailTarget.innerHTML = '';
});

refreshJobsButton.addEventListener('click', loadJobs);

setInterval(loadJobs, 8000);
loadJobs();
