// 用无头 Chromium 逐帧渲染 scene.html。
//
//   node render.cjs info   <build>             导出时长、场景起点与配乐提示 -> <build>/cues.json
//   node render.cjs stills <build> t1 t2 ...   导出指定时刻的静帧 -> <build>/still_<t>.png
//   node render.cjs video  <build> [workers]   并行渲染视频分段 -> <build>/seg_*.mp4 + segments.txt
const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');

let playwright;
try {
  playwright = require('playwright');
} catch {
  playwright = require(path.join(execSync('npm root -g').toString().trim(), 'playwright'));
}

const FPS = 30;
const W = 1920, H = 1080;
const ROOT = __dirname;

async function openScene(browser) {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  // 所有请求都直接从本地目录读取，不经过网络
  await page.route('http://scene.local/**', route => {
    const rel = decodeURIComponent(new URL(route.request().url()).pathname).replace(/^\/+/, '');
    route.fulfill({ path: path.join(ROOT, rel) });
  });
  page.on('pageerror', e => { console.error('page error:', e.message); process.exitCode = 1; });
  await page.goto('http://scene.local/scene.html');
  await page.evaluate(() => window.ready);
  return page;
}

function encoder(out) {
  const ff = spawn('ffmpeg', [
    '-y', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-g', '60',
    out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res, rej) => ff.on('close', c => (c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`)))));
  return { ff, done };
}

async function renderRange(browser, from, to, out, progress) {
  const page = await openScene(browser);
  const { ff, done } = encoder(out);
  for (let i = from; i < to; i++) {
    await page.evaluate(t => window.render(t), i / FPS);
    const png = await page.screenshot({ type: 'png' });
    if (!ff.stdin.write(png)) await new Promise(r => ff.stdin.once('drain', r));
    progress();
  }
  ff.stdin.end();
  await done;
  await page.close();
}

async function main() {
  const [mode, build, ...rest] = process.argv.slice(2);
  fs.mkdirSync(build, { recursive: true });
  const browser = await playwright.chromium.launch({ args: ['--font-render-hinting=none'] });
  try {
    if (mode === 'info') {
      const page = await openScene(browser);
      const info = await page.evaluate(() => ({ duration: window.DURATION, sceneStarts: window.SCENE_STARTS, cues: window.CUES }));
      fs.writeFileSync(path.join(build, 'cues.json'), JSON.stringify(info, null, 1));
      console.log(`duration ${info.duration.toFixed(2)}s, ${info.cues.length} cues`);
    } else if (mode === 'stills') {
      const page = await openScene(browser);
      for (const t of rest.map(Number)) {
        await page.evaluate(x => window.render(x), t);
        await page.screenshot({ path: path.join(build, `still_${t.toFixed(2)}.png`) });
      }
    } else if (mode === 'video') {
      const workers = Number(rest[0] || 4);
      const page = await openScene(browser);
      const total = Math.ceil((await page.evaluate(() => window.DURATION)) * FPS);
      await page.close();
      const per = Math.ceil(total / workers);
      let doneFrames = 0, last = 0;
      const progress = () => {
        doneFrames++;
        const pct = Math.floor(doneFrames / total * 20);
        if (pct > last) { last = pct; console.log(`frames ${doneFrames}/${total}`); }
      };
      const segs = [];
      const jobs = [];
      for (let w = 0; w < workers; w++) {
        const from = w * per, to = Math.min(total, from + per);
        if (from >= to) break;
        const out = path.join(build, `seg_${w}.mp4`);
        segs.push(out);
        jobs.push(renderRange(browser, from, to, out, progress));
      }
      await Promise.all(jobs);
      fs.writeFileSync(path.join(build, 'segments.txt'), segs.map(s => `file '${path.resolve(s)}'`).join('\n') + '\n');
    } else {
      throw new Error(`unknown mode: ${mode}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
