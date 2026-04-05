import nodemailer from 'nodemailer'

function getTransportConfig() {
  const host = process.env.SMTP_HOST
  const port = Number(process.env.SMTP_PORT ?? '587')
  const user = process.env.SMTP_USER
  const pass = process.env.SMTP_PASS

  if (!host || !port || !user || !pass) {
    throw new Error('SMTP credentials are not fully configured')
  }

  return {
    host,
    port,
    secure: port === 465,
    auth: {
      user,
      pass,
    },
  }
}

export async function sendResetPasswordEmail({ to, username, resetLink }) {
  const from = process.env.SMTP_FROM ?? process.env.SMTP_USER
  if (!from) {
    throw new Error('SMTP_FROM or SMTP_USER must be configured')
  }

  const transporter = nodemailer.createTransport(getTransportConfig())
  const subject = 'Reset hasla - Family Food Planner'
  const text = [
    `Czesc ${username},`,
    '',
    'Otrzymalismy prosbe o reset hasla.',
    `Kliknij link aby ustawic nowe haslo: ${resetLink}`,
    '',
    'Link wygasa po 30 minutach.',
    'Jesli to nie Ty, zignoruj te wiadomosc.',
  ].join('\n')

  const html = `
    <p>Czesc <strong>${username}</strong>,</p>
    <p>Otrzymalismy prosbe o reset hasla.</p>
    <p><a href="${resetLink}">Kliknij tutaj, aby ustawic nowe haslo</a></p>
    <p>Link wygasa po 30 minutach.</p>
    <p>Jesli to nie Ty, zignoruj te wiadomosc.</p>
  `

  await transporter.sendMail({
    from,
    to,
    subject,
    text,
    html,
  })
}
