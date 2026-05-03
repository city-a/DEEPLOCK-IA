// server.js - El cerebro que maneja los pagos con Mercado Pago
const express = require('express');
const mercadopago = require('mercadopago');
const nodemailer = require('nodemailer');
const cors = require('cors');
const crypto = require('crypto');
require('dotenv').config();

const app = express();
app.use(cors());
app.use(express.json());

// ================= CONFIGURACIÓN DE MERCADO PAGO =================
mercadopago.configure({
    access_token: process.env.MP_ACCESS_TOKEN  // Esta llave la pondrás en el paso 6
});

// ================= CONFIGURACIÓN DE CORREO (GMAIL) =================
const transporter = nodemailer.createTransport({
    host: 'smtp.gmail.com',
    port: 587,
    secure: false,
    auth: {
        user: process.env.EMAIL_USER,  // Tu correo de Gmail
        pass: process.env.EMAIL_PASS   // Una contraseña especial que sacarás de Gmail
    }
});

// ================= ENDPOINT PARA CREAR EL BOTÓN DE PAGO =================
app.post('/api/create-preference', async (req, res) => {
    try {
        const { plan, price, email, planName } = req.body;

        // Creamos la preferencia de pago (como una factura)
        let preference = {
            items: [{
                title: planName,
                quantity: 1,
                unit_price: Number(price),
                currency_id: 'COP'  // Pesos colombianos
            }],
            payer: { email: email },
            back_urls: {
                success: 'http://localhost:3000/success',
                failure: 'http://localhost:3000/failure',
                pending: 'http://localhost:3000/pending'
            },
            auto_return: 'approved',
            notification_url: 'https://tusitio.com/api/mercadopago-webhook'  // DESPUÉS lo cambias
        };

        const response = await mercadopago.preferences.create(preference);
        res.json({ init_point: response.body.init_point });
    } catch (error) {
        console.error(error);
        res.status(500).json({ error: 'Error al crear el pago' });
    }
});

// ================= WEBHOOK: LA CAMPANA QUE AVISA CUANDO PAGAN =================
app.post('/api/mercadopago-webhook', async (req, res) => {
    const paymentId = req.body.data?.id;
    if (paymentId) {
        try {
            const payment = await mercadopago.payment.findById(paymentId);
            if (payment.body.status === 'approved') {
                // Enviar correo de confirmación
                const userEmail = payment.body.payer.email;
                const planName = payment.body.additional_info.items[0].title;
                const amount = payment.body.transaction_amount;

                const mailOptions = {
                    from: `"Deeplock IA" <${process.env.EMAIL_USER}>`,
                    to: userEmail,
                    subject: '✅ ¡Pago exitoso! Ya puedes editar tu bot',
                    html: `
                        <h2>¡Gracias por tu compra, ${userEmail}!</h2>
                        <p>Pagaste <strong>$${amount.toLocaleString()} COP</strong> por el plan <strong>${planName}</strong>.</p>
                        <p>Haz clic aquí para empezar a crear tu bot:</p>
                        <a href="https://tusitio.com/editor" style="background:#22c55e; color:white; padding:12px 24px; text-decoration:none; border-radius:30px;">EDITAR MI BOT</a>
                    `
                };
                await transporter.sendMail(mailOptions);
                console.log(`Correo enviado a ${userEmail}`);
            }
        } catch (error) {
            console.error('Error:', error);
        }
    }
    res.status(200).send('OK');
});

// ================= INICIAR EL SERVIDOR =================
const PORT = process.env.PORT || 3000;
app.listen(PORT, () => {
    console.log(`✅ Servidor funcionando en http://localhost:${PORT}`);
});