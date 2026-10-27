// 작업실과 운영 현황이 함께 쓰는 관문 정의. 코드는 agentic-character-factory 명세의 관문 코드를 따른다.
// kind: pick = 후보 중 하나를 고르는 관문(작업실에서만 결정), approve = 결과를 검토하고 승인하는 관문.
// G4b(자세·의상)는 이 데모에 아직 넣지 않았다.
// 얼굴은 G1에서 한 번만 고른다. S2는 고른 얼굴로 기준 사진을 만들고 같은 사람인지 자동 검사한다(사람 관문 없음).
window.FACTORY_GATES = [
  { code: 'G1', title: '얼굴 고르기', kind: 'pick', stage: 'S1', team: 'visual', step: 'face' },
  { code: 'G3', title: '기획안 고르기', kind: 'pick', stage: 'S3', team: 'plan', step: 'plan' },
  { code: 'G4a', title: '챕터 배경 고르기', kind: 'pick', stage: 'S4a', team: 'visual', step: 'bg' },
  { code: 'G4', title: '완성 이미지 승인', kind: 'approve', stage: 'S4', team: 'visual', step: 'frames' },
  { code: 'G5b', title: '움직임 고르기', kind: 'pick', stage: 'S6', team: 'video', step: 'motion' },
  { code: 'G6', title: '페르소나 승인', kind: 'approve', stage: 'S8', team: 'persona' },
  { code: 'G7', title: '데이터 표본 검수', kind: 'approve', stage: 'S9', team: 'data' }
];
window.FACTORY_GATE = (code) => window.FACTORY_GATES.find((g) => g.code === code);

