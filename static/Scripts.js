// Toggle notification popup visibility
function toggleNotification() {
  const popup = document.getElementById("notificationPopup");
  popup.classList.toggle("hidden");
}

// Check if there's a leak based on valve status and flow rate
function checkForLeak(valveStatus, flowRate) {
  const leakThreshold = 0.5; // L/min threshold for detecting leaks
  return valveStatus === "Closed" && flowRate > leakThreshold;
}

// Update leak status card UI
function updateLeakStatus(valveStatus, flowRate) {
  const leakDetected = checkForLeak(valveStatus, flowRate);
  const leakCard = document.getElementById("leak-card");
  const statusText = document.getElementById("leak-status");

  if (leakDetected) {
    leakCard.style.backgroundColor = "#ffdddd";
    leakCard.style.border = "2px solid red";
    statusText.textContent = "Status: Leak Detected 🚨";
    statusText.style.color = "red";
  } else {
    leakCard.style.backgroundColor = "#ddffdd";
    leakCard.style.border = "2px solid green";
    statusText.textContent = "Status: No Leak ✅";
    statusText.style.color = "green";
  }
}

// Example usage — replace with live sensor data
let valveStatus = "Closed"; // Update dynamically from sensors
let flowRate = 1.0;         // Update dynamically from sensors

updateLeakStatus(valveStatus, flowRate);

// Optional helper to set leak status with classes and text
function setLeakStatus(isLeaking) {
  const leakStatus = document.getElementById('leak-status');
  const leakText = document.getElementById('leak-text');
  // const leakIcon = document.getElementById('leak-icon'); // Unused

  if (isLeaking) {
    leakStatus.classList.add('leak-active');
    leakText.textContent = "Leak Detected";
  } else {
    leakStatus.classList.remove('leak-active');
    leakText.textContent = "No Leak";
  }
}

// Login form submit handler - sends POST to /login and handles response
document.getElementById('login-form').addEventListener('submit', async (e) => {
  e.preventDefault();

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value.trim();
  const errorMessage = document.getElementById('login-error');
  errorMessage.textContent = ''; // clear previous errors

  if (!username || !password) {
    errorMessage.textContent = 'Please enter username and password.';
    return;
  }

  try {
    const response = await fetch('/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password })
    });

    const result = await response.json();

    if (response.ok && result.redirect) {
      window.location.href = result.redirect;
    } else {
      errorMessage.textContent = result.error || 'Login failed';
    }
  } catch (err) {
    errorMessage.textContent = 'Server error. Please try again later.';
    console.error('Login error:', err);
  }
});
