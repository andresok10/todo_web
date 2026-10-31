import calendar
from decimal import ROUND_HALF_UP, Decimal

import pendulum
from babel.dates import get_month_names
from flask import Blueprint, render_template, request
from flask_wtf import FlaskForm
from wtforms import DecimalField, StringField
from wtforms.validators import InputRequired, NumberRange

app1 = Blueprint("calendario", __name__)


class FormEdad(FlaskForm):
    fecha = StringField("Fecha de nacimiento", validators=[InputRequired()])


class FormDescuento(FlaskForm):
    monto = DecimalField("Monto", validators=[InputRequired(), NumberRange(min=0)])
    porc = DecimalField("Porcentaje", validators=[InputRequired(), NumberRange(min=0, max=100)])


@app1.route("/", methods=["GET", "POST"])
def calendario_app():
    ahora = pendulum.now("America/Guayaquil")
    hoy = ahora.start_of("day")
    f1, f2 = FormEdad(), FormDescuento()
    nombres = get_month_names("wide", locale="es")
    meses = [{"nombre": nombres[m], "mes_numero": m, "semanas": calendar.Calendar().monthdayscalendar(ahora.year, m)} for m in range(ahora.month, 13)]
    edad_anos = edad_meses = edad_dias = None
    signo = fn = cumple = msg = ""
    diff_data = descuento = None
    accion = request.form.get("accion")
    if request.method == "POST" and accion == "edad":
        fecha = f1.fecha.data
        if f1.validate_on_submit() and fecha is not None:
            try:
                nacimiento = pendulum.from_format(fecha.strip(), "DD/MM/YYYY", tz="America/Guayaquil")
                if nacimiento > hoy:
                    raise ValueError("Fecha futura")
                periodo = nacimiento.diff(hoy)
                edad_anos, edad_meses, edad_dias = periodo.years, periodo.months, periodo.remaining_days
                # El 29 de febrero se celebra el 28 en los años no bisiestos.
                cumple_d = nacimiento.set(year=hoy.year, day=min(nacimiento.day, calendar.monthrange(hoy.year, nacimiento.month)[1]))
                if cumple_d < hoy:
                    year = hoy.year + 1
                    cumple_d = nacimiento.set(year=year, day=min(nacimiento.day, calendar.monthrange(year, nacimiento.month)[1]))
                diff_data = {"target": cumple_d.int_timestamp * 1000}
                limites = [
                    (120, "Capricornio"),
                    (219, "Acuario"),
                    (321, "Piscis"),
                    (420, "Aries"),
                    (521, "Tauro"),
                    (621, "Géminis"),
                    (723, "Cáncer"),
                    (823, "Leo"),
                    (923, "Virgo"),
                    (1023, "Libra"),
                    (1122, "Escorpio"),
                    (1222, "Sagitario"),
                    (1232, "Capricornio"),
                ]
                signo = next(nombre for limite, nombre in limites if nacimiento.month * 100 + nacimiento.day < limite)
                fn, cumple = nacimiento.format("DD/MM/YYYY"), cumple_d.format("DD/MM/YYYY")
            except ValueError:
                msg = "Ingresa una fecha válida, no futura, con formato DD/MM/AAAA."
        else:
            msg = "Ingresa tu fecha de nacimiento."
    elif request.method == "POST" and accion == "descuento":
        monto, porcentaje = f2.monto.data, f2.porc.data
        if f2.validate_on_submit() and monto is not None and porcentaje is not None:
            descuento = (monto * (1 - porcentaje / Decimal(100))).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            msg = "Ingresa un monto mayor o igual a cero y un porcentaje entre 0 y 100."
    elif request.method == "POST":
        msg = "Selecciona una operación válida."
    return render_template(
        "app.html",
        ahora=ahora,
        meses=meses,
        f1=f1,
        f2=f2,
        edad_anos=edad_anos,
        edad_meses=edad_meses,
        edad_dias=edad_dias,
        signo=signo,
        fn=fn,
        cumple=cumple,
        diff_data=diff_data,
        descuento=descuento,
        msg=msg,
    )
