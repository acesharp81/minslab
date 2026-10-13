import math
# EPSG:5186  Korea 2000 / Central Belt 2010  (GRS80, lon0=127, lat0=38, k=1, FE=200000, FN=600000)
a=6378137.0; f=1/298.257222101; e2=f*(2-f); ep2=e2/(1-e2)
lon0=math.radians(127.0); lat0=math.radians(38.0); k0=1.0; FE=200000.0; FN=600000.0
def _m(phi):
    e4=e2*e2; e6=e4*e2
    return a*((1-e2/4-3*e4/64-5*e6/256)*phi-(3*e2/8+3*e4/32+45*e6/1024)*math.sin(2*phi)+(15*e4/256+45*e6/1024)*math.sin(4*phi)-(35*e6/3072)*math.sin(6*phi))
M0=_m(lat0)
def forward(lon,lat):
    phi=math.radians(lat); lam=math.radians(lon)
    N=a/math.sqrt(1-e2*math.sin(phi)**2); T=math.tan(phi)**2; C=ep2*math.cos(phi)**2; A=(lam-lon0)*math.cos(phi)
    M=_m(phi)
    x=FE+k0*N*(A+(1-T+C)*A**3/6+(5-18*T+T*T+72*C-58*ep2)*A**5/120)
    y=FN+k0*(M-M0+N*math.tan(phi)*(A*A/2+(5-T+9*C+4*C*C)*A**4/24+(61-58*T+T*T+600*C-330*ep2)*A**6/720))
    return x,y
def inverse(x,y):
    e1=(1-math.sqrt(1-e2))/(1+math.sqrt(1-e2))
    M=M0+(y-FN)/k0; mu=M/(a*(1-e2/4-3*e2**2/64-5*e2**3/256))
    phi1=mu+(3*e1/2-27*e1**3/32)*math.sin(2*mu)+(21*e1**2/16-55*e1**4/32)*math.sin(4*mu)+(151*e1**3/96)*math.sin(6*mu)+(1097*e1**4/512)*math.sin(8*mu)
    C1=ep2*math.cos(phi1)**2; T1=math.tan(phi1)**2; N1=a/math.sqrt(1-e2*math.sin(phi1)**2); R1=a*(1-e2)/(1-e2*math.sin(phi1)**2)**1.5; D=(x-FE)/(N1*k0)
    phi=phi1-(N1*math.tan(phi1)/R1)*(D*D/2-(5+3*T1+10*C1-4*C1*C1-9*ep2)*D**4/24+(61+90*T1+298*C1+45*T1*T1-252*ep2-3*C1*C1)*D**6/720)
    lam=lon0+(D-(1+2*T1+C1)*D**3/6+(5-2*C1+28*T1-3*C1*C1+8*ep2+24*T1*T1)*D**5/120)/math.cos(phi1)
    return math.degrees(lam),math.degrees(phi)
if __name__=='__main__':
    for lon,lat in [(126.7378,37.5375),(126.7146,37.5531),(127.0,38.0),(126.9780,37.5665)]:
        x,y=forward(lon,lat); l2,p2=inverse(x,y); print(f'{lon},{lat} -> x={x:.2f} y={y:.2f} -> back {l2:.7f},{p2:.7f}  err {abs(l2-lon)*88000:.4f}m/{abs(p2-lat)*111000:.4f}m')
    # published reference: Seoul City Hall (126.9780, 37.5665) in EPSG:5186 is approx x=198,000.. y=551,500..
