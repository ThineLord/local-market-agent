/* An original procedural architectural study of a charging bull.
   Local geometry only; no remote assets, textures or render dependencies. */
const TAU = Math.PI * 2;
const mix = (a, b, t) => a + (b - a) * t;
const add = (a, b) => a.map((n, i) => n + b[i]);
const scale = (a, s) => a.map(n => n * s);
const cross = (a, b) => [a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0]];
const unit = a => scale(a, 1 / (Math.hypot(...a) || 1));

function buildBull() {
  const vertices = [], faces = [], lines = [];
  const vertex = p => { vertices.push(p); return vertices.length - 1; };
  // Longitudinal sections form a continuous torso, neck and lowered skull.
  function loft(sections, sides = 18) {
    const start = vertices.length;
    sections.forEach(([x,y,z,ry,rz], i) => {
      for(let j=0;j<sides;j++) {
        const angle = j / sides * TAU;
        vertex([x, y + Math.cos(angle)*ry, z + Math.sin(angle)*rz]);
      }
    });
    for(let i=0;i<sections.length-1;i++) for(let j=0;j<sides;j++) {
      const a=start+i*sides+j, b=start+i*sides+(j+1)%sides;
      const c=start+(i+1)*sides+j, d=start+(i+1)*sides+(j+1)%sides;
      faces.push([a,b,c],[b,d,c]);
    }
  }
  function ellipsoid(center, radii, rings=8, sides=14, tilt=0) {
    const start=vertices.length;
    for(let i=0;i<=rings;i++) {
      const t=Math.PI*i/rings, r=Math.sin(t);
      for(let j=0;j<sides;j++) {
        const p=[Math.cos(t)*radii[0],r*Math.cos(TAU*j/sides)*radii[1],r*Math.sin(TAU*j/sides)*radii[2]];
        vertex(add(center,[p[0]*Math.cos(tilt)-p[1]*Math.sin(tilt),p[0]*Math.sin(tilt)+p[1]*Math.cos(tilt),p[2]]));
      }
    }
    for(let i=0;i<rings;i++) for(let j=0;j<sides;j++) {
      const a=start+i*sides+j,b=start+i*sides+(j+1)%sides,c=a+sides,d=b+sides;
      faces.push([a,b,c],[b,d,c]);
    }
  }
  function tube(points, radii, sides=9) {
    const start=vertices.length;
    for(let i=0;i<points.length;i++) {
      const before=points[Math.max(0,i-1)],after=points[Math.min(points.length-1,i+1)];
      const tangent=unit(after.map((v,k)=>v-before[k]));
      const axis=Math.abs(tangent[1])>.9?[1,0,0]:[0,1,0];
      const u=unit(cross(tangent,axis)),v=unit(cross(tangent,u));
      for(let j=0;j<sides;j++) vertex(add(points[i],add(scale(u,Math.cos(j/sides*TAU)*radii[i]),scale(v,Math.sin(j/sides*TAU)*radii[i]))));
    }
    for(let i=0;i<points.length-1;i++) for(let j=0;j<sides;j++) {
      const a=start+i*sides+j,b=start+i*sides+(j+1)%sides,c=a+sides,d=b+sides;
      faces.push([a,b,c],[b,d,c]);
    }
  }
  loft([
    [-2.05,2.03,0,.15,.19],[-1.86,2.1,0,.57,.55],[-1.5,2.13,0,.77,.72],
    [-1.1,2.12,0,.73,.75],[-.65,2.12,0,.66,.69],[-.2,2.12,0,.72,.73],
    [.25,2.17,0,.88,.8],[.65,2.23,0,1,.85],[1,2.18,0,.96,.8],
    [1.25,2.02,0,.83,.7],[1.48,1.77,0,.65,.57],[1.67,1.55,0,.58,.54],
    [1.88,1.38,0,.56,.56],[2.13,1.23,0,.46,.47],[2.4,1.09,0,.33,.36],
    [2.64,1.04,0,.24,.34],[2.79,1.07,0,.18,.28]
  ],20);
  // Muscular shoulder and haunch volumes; legs sweep into a charging stance.
  for(const side of [-1,1]) {
    ellipsoid([.73,1.94,.58*side],[.62,.8,.43],8,14,-.16);
    ellipsoid([-1.43,1.98,.53*side],[.58,.66,.42],8,14,.2);
    const offset=side===1?0:.28;
    tube([[.88,1.91,side*.63],[1.05,1.48,side*.69],[1.13,1.08,side*.73],[1.48+offset,.63,side*.8],[1.69+offset,.25,side*.85],[1.75+offset,.13,side*.85]],[.34,.29,.21,.14,.12,.17],10);
    ellipsoid([1.83+offset,.13,.85*side],[.26,.14,.2],4,10);
    tube([[-1.5,1.89,side*.61],[-1.62,1.4,side*.69],[-1.33,1.02,side*.75],[-1.86-offset,.59,side*.8],[-2.03-offset,.23,side*.86],[-1.96-offset,.12,side*.86]],[.38,.32,.22,.14,.12,.17],10);
    ellipsoid([-1.89-offset,.12,.86*side],[.25,.13,.2],4,10);
    // Horns extend out of the forehead then curl upward into fine points.
    tube([[1.81,1.69,.41*side],[1.82,1.82,.68*side],[1.77,1.94,.95*side],[1.69,2.12,1.18*side],[1.68,2.38,1.32*side],[1.78,2.63,1.34*side],[1.92,2.79,1.26*side]],[.19,.17,.14,.11,.075,.04,.002],10);
    ellipsoid([1.55,1.72,.66*side],[.25,.1,.27],5,10,side*.1);
    ellipsoid([2.04,1.47,.47*side],[.1,.065,.04],4,8,-.3);
    ellipsoid([2.65,1.14,.275*side],[.085,.055,.04],4,8);
  }
  // Raised, curling tail.
  tube([[-1.99,2.38,0],[-2.3,2.59,.06],[-2.57,2.84,.13],[-2.65,3.12,.22],[-2.48,3.34,.31],[-2.18,3.37,.4],[-2.01,3.19,.48],[-2.09,2.99,.52]],[.09,.083,.07,.06,.053,.045,.04,.035],7);
  ellipsoid([-2.1,2.95,.53],[.09,.18,.09],5,8,-.3);
  // Plinth and restrained construction lines anchor the sculpture in space.
  const plinth=[[-3,-.08,-1.65],[3.25,-.08,-1.65],[3.25,-.08,1.65],[-3,-.08,1.65]];
  for(let j=0;j<4;j++) {
    lines.push([plinth[j],plinth[(j+1)%4],.7]);
    lines.push([add(plinth[j],[0,-.13,0]),add(plinth[(j+1)%4],[0,-.13,0]),.35]);
    lines.push([plinth[j],add(plinth[j],[0,-.13,0]),.4]);
  }
  for(let x=-4;x<=4;x+=.5)lines.push([[x,-.24,-2.7],[x,-.24,2.7],.07]);
  for(let z=-2.5;z<=2.5;z+=.5)lines.push([[-4,-.24,z],[4,-.24,z],.07]);
  lines.push([[-3,-.22,2.06],[3.25,-.22,2.06],.3]);
  for(const x of [-3,3.25])lines.push([[x,-.22,1.92],[x,-.22,2.2],.4]);
  return {vertices,faces,lines};
}

export function createBullScene(canvas) {
  const ctx=canvas.getContext('2d');
  if(!ctx)return {navigate(){},detail(){},setPaused(){}};
  const mesh=buildBull();
  const reduce=window.matchMedia('(prefers-reduced-motion: reduce)');
  let width=0,height=0,paused=false,visible=true,raf=0,last=0,time=0;
  const current={yaw:-.48,pitch:.16,zoom:1,x:.74,y:.43};
  let target={...current}, page='overview', depth=false;
  const views={overview:[-.48,.16,1,.74,.43],watchlist:[-.8,.23,1.03,.81,.47],briefs:[-.22,.13,1.13,.8,.44],signals:[-.95,.19,.95,.75,.48],risk:[-.38,.28,1.05,.8,.46],ledger:[.25,.16,.98,.77,.47],audit:[-.65,.32,1.05,.8,.48],performance:[-.1,.19,1.1,.77,.46],operations:[-.9,.24,1.03,.78,.49],settings:[.35,.22,1,.8,.48]};
  function updateTarget() {
    const [yaw,pitch,zoom,x,y]=views[page]||views.overview;
    target={yaw:yaw+(depth?.3:0),pitch,zoom:zoom*(depth?.92:1),x:x-(depth?.12:0),y};
  }
  function project(p,yaw,pitch,zoom) {
    const x=p[0]*Math.cos(yaw)+p[2]*Math.sin(yaw);
    const z=-p[0]*Math.sin(yaw)+p[2]*Math.cos(yaw);
    const y=(p[1]-1.35)*Math.cos(pitch)-z*Math.sin(pitch);
    const d=(p[1]-1.35)*Math.sin(pitch)+z*Math.cos(pitch);
    const perspective=10/(10+d);
    const s=Math.min(width*.135,height*.135)*zoom*(width<700?.83:1);
    return [width*(width<700?Math.min(current.x,.65):current.x)+x*s*perspective,height*current.y-y*s*perspective,d];
  }
  function draw(dt=0) {
    if(!paused&&!reduce.matches)time+=dt;
    const ease=reduce.matches||paused?1:1-Math.exp(-dt*3.3);
    for(const key of Object.keys(current))current[key]=mix(current[key],target[key],ease);
    const drift=paused||reduce.matches?0:Math.sin(time*.15)*.035;
    const yaw=current.yaw+drift,pitch=current.pitch,zoom=current.zoom;
    ctx.clearRect(0,0,width,height);
    // A transparent ground shadow, never a solid 3D render.
    const ground=project([0,-.2,0],yaw,pitch,zoom);
    const glow=ctx.createRadialGradient(ground[0],ground[1],0,ground[0],ground[1],width*.28);
    glow.addColorStop(0,'rgba(169,151,110,0.065)');glow.addColorStop(1,'rgba(169,151,110,0)');
    ctx.fillStyle=glow;ctx.fillRect(0,0,width,height);
    for(const [a,b,opacity] of mesh.lines) {
      const p=project(a,yaw,pitch,zoom),q=project(b,yaw,pitch,zoom);
      ctx.beginPath();ctx.moveTo(p[0],p[1]);ctx.lineTo(q[0],q[1]);ctx.strokeStyle=`rgba(161,143,103,${opacity})`;ctx.lineWidth=.65;ctx.stroke();
    }
    const points=mesh.vertices.map(v=>project(v,yaw,pitch,zoom));
    const sorted=mesh.faces.map(f=>({f,z:f.reduce((s,i)=>s+points[i][2],0)/3})).sort((a,b)=>b.z-a.z);
    for(const {f,z} of sorted) {
      const a=points[f[0]],b=points[f[1]],c=points[f[2]];
      // Opaque paper facets provide hidden-line removal and a sculptural silhouette.
      ctx.beginPath();ctx.moveTo(a[0],a[1]);ctx.lineTo(b[0],b[1]);ctx.lineTo(c[0],c[1]);ctx.closePath();
      ctx.fillStyle='rgba(246,245,240,.91)';ctx.fill();
      ctx.strokeStyle=`rgba(159,133,82,${Math.max(.16,Math.min(.53,.36-z*.07))})`;ctx.lineWidth=.68;ctx.stroke();
    }
  }
  function tick(stamp) {
    raf=0;if(!visible)return;
    if(!paused&&!reduce.matches&&stamp-last<32){raf=requestAnimationFrame(tick);return;}
    const dt=Math.min(.05,(stamp-last)/1000||.016);last=stamp;
    draw(dt);
    if(!paused&&!reduce.matches)raf=requestAnimationFrame(tick);
  }
  function wake() {if(!raf&&visible){last=performance.now();raf=requestAnimationFrame(tick);}}
  function resize() {
    const rect=canvas.getBoundingClientRect();width=rect.width;height=rect.height;
    const dpr=Math.min(devicePixelRatio||1,2);canvas.width=Math.round(width*dpr);canvas.height=Math.round(height*dpr);ctx.setTransform(dpr,0,0,dpr,0,0);wake();
  }
  new ResizeObserver(resize).observe(canvas);
  document.addEventListener('visibilitychange',()=>{visible=!document.hidden;if(!visible&&raf){cancelAnimationFrame(raf);raf=0;}else wake();});
  reduce.addEventListener('change',wake);
  return {
    navigate(next){page=next;updateTarget();wake();},
    detail(open){depth=open;updateTarget();wake();},
    setPaused(value){paused=value;wake();}
  };
}
