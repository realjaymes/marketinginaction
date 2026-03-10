// ===========================
// Theme Toggle
// ===========================
const themeToggle = document.getElementById('themeToggle');
const html = document.documentElement;

// Load saved theme or default to dark
const savedTheme = localStorage.getItem('theme') || 'dark';
html.setAttribute('data-theme', savedTheme);

themeToggle.addEventListener('click', () => {
  const current = html.getAttribute('data-theme');
  const next = current === 'dark' ? 'light' : 'dark';
  html.setAttribute('data-theme', next);
  localStorage.setItem('theme', next);
});

// ===========================
// Progress Bar
// ===========================
const progressBar = document.getElementById('progressBar');

function updateProgress() {
  const scrollTop = window.scrollY;
  const docHeight = document.documentElement.scrollHeight - window.innerHeight;
  const progress = docHeight > 0 ? (scrollTop / docHeight) * 100 : 0;
  progressBar.style.width = progress + '%';
}

window.addEventListener('scroll', updateProgress, { passive: true });

// ===========================
// Section Nav Active State
// ===========================
const sections = document.querySelectorAll('.content-section');
const navItems = document.querySelectorAll('.section-nav-item');

function updateActiveNav() {
  const scrollPos = window.scrollY + 180;

  let currentSection = null;
  sections.forEach((section) => {
    if (section.offsetTop <= scrollPos) {
      currentSection = section.id;
    }
  });

  navItems.forEach((item) => {
    const sectionId = 'section-' + item.getAttribute('data-section');
    if (sectionId === currentSection) {
      item.classList.add('active');
    } else {
      item.classList.remove('active');
    }
  });
}

window.addEventListener('scroll', updateActiveNav, { passive: true });

// ===========================
// Concept Blocks (Collapsible)
// ===========================
document.querySelectorAll('.concept-toggle').forEach((toggle) => {
  toggle.addEventListener('click', () => {
    const content = toggle.nextElementSibling;
    const icon = toggle.querySelector('.toggle-icon');
    const isExpanded = content.classList.contains('expanded');

    content.classList.toggle('expanded');
    toggle.setAttribute('aria-expanded', !isExpanded);
    icon.innerHTML = isExpanded ? '&#9654;' : '&#9660;';
  });
});

// ===========================
// File Explorer
// ===========================
document.querySelectorAll('.file-toggle').forEach((toggle) => {
  toggle.addEventListener('click', () => {
    const fileId = 'file-' + toggle.getAttribute('data-file');
    const details = document.getElementById(fileId);

    // Close others
    document.querySelectorAll('.file-details').forEach((d) => {
      if (d.id !== fileId) {
        d.classList.remove('expanded');
      }
    });

    details.classList.toggle('expanded');
  });
});

// ===========================
// Tabs
// ===========================
document.querySelectorAll('.tabs').forEach((tabGroup) => {
  const buttons = tabGroup.querySelectorAll('.tab-btn');

  buttons.forEach((btn) => {
    btn.addEventListener('click', () => {
      const targetId = btn.getAttribute('data-tab');

      // Find parent section to scope the tab content search
      const parentSection = tabGroup.closest('.concept-content, .section-body, .content-section');
      if (!parentSection) return;

      // Deactivate all tabs in this group
      buttons.forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');

      // Show/hide content
      parentSection.querySelectorAll('.tab-content').forEach((content) => {
        if (content.id === targetId) {
          content.classList.add('active');
        } else {
          content.classList.remove('active');
        }
      });
    });
  });
});

// ===========================
// Copy to Clipboard
// ===========================
document.querySelectorAll('.copy-btn').forEach((btn) => {
  btn.addEventListener('click', () => {
    const codeBlock = btn.closest('.code-block');
    const code = codeBlock.querySelector('code');
    const text = code.textContent;

    navigator.clipboard.writeText(text).then(() => {
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'Copy';
        btn.classList.remove('copied');
      }, 2000);
    }).catch(() => {
      // Fallback for older browsers
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
      btn.textContent = 'Copied!';
      btn.classList.add('copied');
      setTimeout(() => {
        btn.textContent = 'Copy';
        btn.classList.remove('copied');
      }, 2000);
    });
  });
});

// ===========================
// Smooth scroll for nav items
// ===========================
document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
  anchor.addEventListener('click', (e) => {
    const targetId = anchor.getAttribute('href');
    if (targetId === '#') return;

    const target = document.querySelector(targetId);
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});
