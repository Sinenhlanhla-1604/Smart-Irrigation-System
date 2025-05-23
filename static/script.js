function showPlan(plan, button) {
  const plans = {
    basic: {
      title: 'Basic Plan – "Monitor"',
      price: 'R500 / month',
      desc: 'Ideal for small-scale farms (up to 1 hectare). Includes full sensor readings for tank level, pulse meter, reed safe sensor, temperature alerts, and aqua level sensor. Provides dashboard alerts and Sigfox network connectivity to help monitor irrigation more efficiently.'
    },
    standard: {
      title: 'Standard Plan – "Insight"',
      price: 'R850 / month',
      desc: 'Perfect for medium-sized farms (1–3 hectares). Includes all sensor readings (tank level, pulse meter, reed safe sensor, temperature alert, and aqua level sensor) with expanded dashboard features and real-time alerts to optimize irrigation decisions.'
    },
    advanced: {
      title: 'Advanced Plan – "Control"',
      price: 'R1,200 / month',
      desc: 'Designed for farms needing more detailed insights. Includes all sensors (tank level, pulse meter, reed safe sensor, temperature alert, and aqua level sensor) with advanced reporting, leak detection, and historical data for improved irrigation management.'
    },
    premium: {
      title: 'Premium Plan – "Automate"',
      price: 'R1,800 / month',
      desc: 'For farms ready to automate irrigation. Includes all sensor data (tank level, pulse meter, reed safe sensor, temperature alert, and aqua level sensor) with full automation, intelligent irrigation scheduling, and real-time health monitoring for efficient operation.'
    },
    enterprise: {
      title: 'Enterprise Plan',
      price: 'Custom pricing',
      desc: 'For large farms requiring custom integrations and extensive support. Includes all sensor readings, fully automated irrigation, custom analytics, system API integrations, and dedicated support tailored to the needs of large-scale farming operations.'
    }
  };

  // Update the displayed plan
  const planDisplay = document.getElementById('planDisplay');
  planDisplay.innerHTML = `
    <h3>${plans[plan].title}</h3>
    <p>${plans[plan].price}</p>
    <p>${plans[plan].desc}</p>
  `;
  
  // Update the active tab
  const buttons = document.querySelectorAll('.pricing-tabs button');
  buttons.forEach(btn => btn.classList.remove('active'));
  button.classList.add('active');
}


//login//
document.getElementById('login-form').addEventListener('submit', function (e) {
  e.preventDefault();

  const username = document.getElementById('username').value.trim();
  const password = document.getElementById('password').value.trim();
  const errorMessage = document.getElementById('login-error');

  // Simulated login credentials
  const validUser = "admin";
  const validPass = "admin123";

  if (username === validUser && password === validPass) {
    // Redirect to dashboard
    window.location.href = "index.html";
  } else {
    errorMessage.textContent = "Invalid username or password";
  }
});

