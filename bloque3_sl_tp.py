# ==============================
# BLOQUE 3 – POSICIONES (Entradas, SL, TP, RBB, % Win/Fail)
# ==============================

import pandas as pd
from IPython.display import HTML, display

# --- AUX: Determinar Dirección según tendencias calculadas en Bloque 1 ---
def obtener_direccion(data, tf):
    etiquetas = {
        "Tendencia_Alcista": "Tendencia Alcista",
        "Tendencia_Bajista": "Tendencia Bajista",
        "Lateral_sesgo_Alcista": "Lateral Alcista",
        "Lateral_sin_sesgo":     "Lateral Alcista",
        "Lateral_sesgo_Bajista": "Lateral Bajista",
    }
    # Buscar clave Trend_bias_{categoria}_{tf}
    for k, v in data.items():
        if k.startswith("Trend_bias_") and k.endswith(f"_{tf}") and isinstance(v, (int, float)):
            for raw, et in etiquetas.items():
                if raw in k:
                    return et
    # Si no hay bias, usar campo generado en Bloque1
    return data.get(f"direccion_{tf}", "-")

# --- AUX: Formatea flotante a entero sin decimales, con separadores miles ---
def formato_entero(x):
    try:
        i = int(round(float(x)))
        s = f"{i:,}"
        return s.replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return x

# --- 1) CÁLCULO DE ENTRADAS -----------------------------------------------
def calcular_entradas(data, tf):
    rt   = float(data.get("Valor_mcdo", 0))
    atr  = float(data.get(f"ATR_{tf}", 0))
    hi   = float(data.get(f"Marco_High_{tf}", 0))
    lo   = float(data.get(f"Marco_Low_{tf}", 0))
    rango = hi - lo + 1e-6

    # 1.1) Separación dinámica según volatilidad
    ratio = atr / rango
    if ratio >= 0.40:
        sep = 0.30 * atr
    elif ratio >= 0.25:
        sep = 0.25 * atr
    else:
        sep = 0.15 * atr

    # 1.2) Delta según tipo de frame y subcaso
    is_estr = evaluar_frame_estructural(data, tf)
    if is_estr:
        adx = float(data.get(f"ADX_{tf}", 0))
        if adx >= umbral_adx_estructura:
            delta, tipo = 0.20 * atr, "agresiva"
        else:
            delta, tipo = 0.15 * atr, "táctica"
    else:
        tz = determinar_frame_proyectado(data, tf)["tipo_zona"].lower()
        if "envolvente" in tz:
            delta, tipo = 0.20 * atr, "táctica"
        elif any(x in tz for x in ("completa","anticipada")):
            delta, tipo = 0.25 * atr, "agresiva"
        else:
            delta, tipo = 0.30 * atr, "conservadora"

    # 1.3) Niveles
    E1 = rt + delta
    E2 = E1 + sep
    E3 = E2 + sep

    # 1.4) Formateo multilinea
    texto = "\n".join([
        f"E1 → {formato_entero(E1)}",
        f"E2 → {formato_entero(E2)}",
        f"E3 → {formato_entero(E3)}"
    ])
    return texto, [E1, E2, E3], tipo

# --- 2) CÁLCULO DE STOP LOSS ----------------------------------------------
def calcular_stop_loss(data, tf, entradas, tipo_entrada):
    atr = float(data.get(f"ATR_{tf}", 0))
    direc = data.get(f"direccion_{tf}", "").lower()

    # 2.1) Factor según tipo
    if evaluar_frame_estructural(data, tf):
        fac_map = {"agresiva":0.20, "táctica":0.15}
    else:
        fac_map = {"agresiva":0.30, "táctica":0.25, "conservadora":0.25}
    factor = fac_map.get(tipo_entrada, 0.25) * atr

    # 2.2) Pivotes y dirección de test
    if "alcista" in direc:
        piv = [data.get(f"Support_pivot_{i}_{tf}") for i in (1,2,3)]
        test = lambda p,ref: isinstance(p,(int,float)) and p<ref
        signo = -1
    else:
        piv = [data.get(f"Resistance_pivot_{i}_{tf}") for i in (1,2,3)]
        test = lambda p,ref: isinstance(p,(int,float)) and p>ref
        signo = +1

    sls=[]; prev=entradas[0]
    for p in piv:
        if test(p, prev): sl = p
        else:             sl = prev + signo*factor
        sls.append(sl); prev=sl

    texto = "\n".join([
        f"SL1 → {formato_entero(sls[0])}",
        f"SL2 → {formato_entero(sls[1])}",
        f"SL3 → {formato_entero(sls[2])}"
    ])
    return texto, sls

# --- 3) CÁLCULO DE TAKE PROFIT --------------------------------------------
def calcular_take_profit(data, tf, entradas):
    atr = float(data.get(f"ATR_{tf}", 0))
    direc = data.get(f"direccion_{tf}", "").lower()
    fac_tp = {1:1.30,2:2.00,3:2.80}

    if "alcista" in direc:
        keys = [f"Resistance_pivot_{i}_{tf}" for i in (1,2,3)]
        cmpf = lambda p,ref: p>ref
    else:
        keys = [f"Support_pivot_{i}_{tf}"    for i in (1,2,3)]
        cmpf = lambda p,ref: p<ref

    TPpiv, TPzon, TPatr = {},{},{}
    prev = entradas[0]
    for i,key in enumerate(keys,1):
        val = data.get(key)
        pv  = float(val) if isinstance(val,(int,float)) else None
        TPpiv[i] = pv if pv is not None and cmpf(pv, prev) else None

        flag = data.get(f"Fibo_zona_envolvente_{tf}",0)
        f78  = data.get(f"Fib_78.6percent_{tf}")
        TPzon[i] = float(f78) if flag and isinstance(f78,(int,float)) else None

        TPatr[i] = prev + fac_tp[i]*atr if "alcista" in direc else prev - fac_tp[i]*atr
        prev = TPpiv[i] or TPatr[i]

    texto = "\n".join([f"TP{i} → {formato_entero(TPpiv[i] or TPatr[i])}" for i in (1,2,3)])
    return texto, TPpiv, TPzon, TPatr

# --- 4) RATIO RIESGO/BENEFICIO ---------------------------------------------
def calcular_rbb(entradas, sls, tps):
    out=[]
    for e,sl,tp in zip(entradas,sls,tps):
        tpv = tp if tp is not None else sl + (sl-e)
        riesgo    = abs(e-sl)
        beneficio = abs(tpv-e)
        if riesgo==0: r="1/∞"
        else:         r=f"1/{int(round(beneficio/ riesgo))}"
        out.append(r)
    return "\n".join(out)

# --- 5) % WIN/FAIL ---------------------------------------------------------
def calcular_win_fail(entradas, sls, tps):
    out=[]
    for e,sl,tp in zip(entradas,sls,tps):
        tpv = tp if tp is not None else sl + (sl-e)
        d_sl = abs(e-sl)
        d_tp = abs(tpv-e)
        total = d_sl + d_tp if (d_sl+d_tp)>0 else 1e-6
        win  = int(round(d_tp/ total *100))
        fail = int(round(d_sl/ total *100))
        out.append(f"{win}%/{fail}%")
    return "\n".join(out)

# --- 6) GENERAR TABLA BLOQUE 3 --------------------------------------------
def generar_tabla_bloque3(data):
    rows=[]
    for tf in detectar_temporalidades(data):
        if not data.get(f"is_valid_{tf}",False): continue
        base={
            "Activo":       data.get("Activo","-"),
            "TF":           tf,
            "Direccion": data.get(f"direccion_{tf}", "-"),
            "Valor actual": formato_entero(data.get("Valor_mcdo")),
            "Frame low":    formato_entero(data.get(f"Marco_Low_{tf}")),
            "Frame high":   formato_entero(data.get(f"Marco_High_{tf}"))
        }
        ent_txt,ent_vals,tp_type = calcular_entradas(data, tf)
        sl_txt,sl_vals          = calcular_stop_loss(data, tf, ent_vals, tp_type)
        tp_txt,tp_p, tp_z, tp_a = calcular_take_profit(data, tf, ent_vals)

        piv_vals = [tp_p[i] or tp_a[i] for i in (1,2,3)]
        zon_vals = [tp_z[i] or tp_a[i] for i in (1,2,3)]
        atr_vals = [tp_a[i] for i in (1,2,3)]

        row={**base,
            "Entrada":         ent_txt,
            "SL":              sl_txt,
            "TP Pivots":       tp_txt,
            "RBB Pivots":      calcular_rbb(ent_vals, sl_vals, piv_vals),
            "% A/F Pivots":    calcular_win_fail(ent_vals, sl_vals, piv_vals),
            "TP zona Técnica": "\n".join([f"TP{i} → {formato_entero(zon_vals[i-1])}" for i in (1,2,3)]),
            "RBB Zona":        calcular_rbb(ent_vals, sl_vals, zon_vals),
            "% A/F Zona":      calcular_win_fail(ent_vals, sl_vals, zon_vals),
            "TP ATR factor":   "\n".join([f"TP{i} → {formato_entero(atr_vals[i-1])}" for i in (1,2,3)]),
            "RBB ATR":         calcular_rbb(ent_vals, sl_vals, atr_vals),
            "% A/F ATR":       calcular_win_fail(ent_vals, sl_vals, atr_vals)
        }
        rows.append(row)
    return rows

# --- 7) EJECUCIÓN Y VISUALIZACIÓN ----------------------------------------
tabla3 = generar_tabla_bloque3(data)
df3 = pd.DataFrame(tabla3, columns=[
    "Activo","TF","Direccion","Valor actual",
    "Frame low","Frame high",
    "Entrada","SL",
    "TP Pivots","RBB Pivots","% A/F Pivots",
    "TP zona Técnica","RBB Zona","% A/F Zona",
    "TP ATR factor","RBB ATR","% A/F ATR"
])

display(HTML("<h2 style='color:#8B4513;'>Bloque 3 – Posiciones (Entradas, SL, TP, RBB, % Win/Fail)</h2>"))
if not df3.empty:
    mostrar_tabla(df3, header_bg="#8B4513", header_fg="#fff", cell_border_color="#444")
else:
    display(HTML("<p>No hay TFs válidos para Bloque 3</p>"))
