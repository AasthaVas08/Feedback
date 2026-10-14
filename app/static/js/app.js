/**
 * Feedback Platform — shared JS utilities.
 * Handles API calls, toast notifications, theme toggle, and user selection.
 */
window.FeedbackApp = (function () {
  'use strict';

  /* ── Theme ───────────────────────────────────────────────────── */
  function initTheme() {
    var saved = localStorage.getItem('fb-theme');
    if (saved) document.documentElement.setAttribute('data-theme', saved);
  }
  function toggleTheme() {
    var current = document.documentElement.getAttribute('data-theme') || 'light';
    var next = current === 'light' ? 'dark' : 'light';
    document.documentElement.setAttribute('data-theme', next);
    localStorage.setItem('fb-theme', next);
  }
  initTheme();

  /* ── User selector (dev mode — no auth) ──────────────────────── */
  var currentUserId = parseInt(localStorage.getItem('fb-user-id') || '1', 10);

  function loadUsers() {
    return api('/api/forms', 'GET').then(function () {
      // Fetch users from a dedicated endpoint or use a fallback
      return fetch('/api/users').then(function (r) { return r.json(); })
        .catch(function () { return []; });
    }).catch(function () { return []; });
  }

  function populateUserSelector(users) {
    var sel = document.getElementById('currentUser');
    if (!sel || !users.length) return;
    sel.innerHTML = '';
    users.forEach(function (u) {
      var opt = document.createElement('option');
      opt.value = u.id;
      opt.textContent = u.name + ' (' + u.role + ')';
      if (u.id === currentUserId) opt.selected = true;
      sel.appendChild(opt);
    });
  }

  function setUser(id) {
    currentUserId = parseInt(id, 10);
    localStorage.setItem('fb-user-id', currentUserId);
  }

  function getUserId() { return currentUserId; }

  /* ── API helper ──────────────────────────────────────────────── */
  function api(url, method, body) {
    var opts = {
      method: method || 'GET',
      headers: { 'Content-Type': 'application/json' }
    };
    if (body) opts.body = JSON.stringify(body);
    return fetch(url, opts).then(function (res) {
      return res.json().then(function (data) {
        if (!res.ok) throw { status: res.status, data: data };
        return data;
      });
    });
  }

  /* ── Toast notifications ─────────────────────────────────────── */
  function toast(message, type) {
    type = type || 'info';
    var container = document.getElementById('toastContainer');
    if (!container) return;
    var el = document.createElement('div');
    el.className = 'toast toast--' + type;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transform = 'translateY(-8px)';
      el.style.transition = 'all 200ms ease-out';
      setTimeout(function () { el.remove(); }, 200);
    }, 3500);
  }

  /* ── Date formatting ─────────────────────────────────────────── */
  function formatDate(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  }
  function formatDateTime(iso) {
    if (!iso) return '—';
    var d = new Date(iso);
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
      + ' ' + d.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' });
  }
  function timeAgo(iso) {
    if (!iso) return '';
    var diff = Date.now() - new Date(iso).getTime();
    var mins = Math.floor(diff / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return mins + 'm ago';
    var hrs = Math.floor(mins / 60);
    if (hrs < 24) return hrs + 'h ago';
    var days = Math.floor(hrs / 24);
    return days + 'd ago';
  }

  /* ── Skeleton helpers ────────────────────────────────────────── */
  function showSkeleton(container, count) {
    count = count || 3;
    var html = '';
    for (var i = 0; i < count; i++) {
      html += '<div class="card" style="margin-bottom:var(--space-4)">'
        + '<div class="skeleton skeleton--title"></div>'
        + '<div class="skeleton skeleton--text"></div>'
        + '<div class="skeleton skeleton--text" style="width:40%"></div>'
        + '</div>';
    }
    container.innerHTML = html;
  }

  /* ── Init user selector on page load ─────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    fetch('/api/users')
      .then(function (r) { return r.json(); })
      .then(function (users) { populateUserSelector(users); })
      .catch(function () { /* no users endpoint yet */ });
  });

  return {
    api: api,
    toast: toast,
    toggleTheme: toggleTheme,
    setUser: setUser,
    getUserId: getUserId,
    formatDate: formatDate,
    formatDateTime: formatDateTime,
    timeAgo: timeAgo,
    showSkeleton: showSkeleton
  };
})();
