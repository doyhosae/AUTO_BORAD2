#!/usr/bin/env python3
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import io
import os
import tempfile
import yaml
from simulate import simulate

# 페이지 설정
st.set_page_config(
    page_title="AUTO_BORAD2 - 게시물 조회수 시뮬레이션",
    page_icon="📊",
    layout="centered"
)

# CSS로 컨테이너 너비 제한
st.markdown("""
<style>
    .main .block-container {
        max-width: 720px;
        padding-top: 2rem;
        padding-bottom: 2rem;
    }
</style>
""", unsafe_allow_html=True)

# 제목
st.title("📊 AUTO_BORAD2 - 게시물 조회수 시뮬레이션")
st.markdown("게시물의 조회수 증가를 현실적으로 시뮬레이션하는 도구입니다.")

# 전역 설정 변수들 (기본값으로 초기화)
if 'simulation_config' not in st.session_state:
    st.session_state.simulation_config = {
        'seed': 20250916,
        'timezone': 'Asia/Seoul',
        'tick_type': '랜덤 범위',
        'tick_duration': '1h',
        'tick_min': '15m',
        'tick_max': '90m',
        'inc_min': 5,
        'inc_max': 60,
        'max_hours': 336,
        'system_hour_cap': None,
        'hourly_weights': {
            "0": 0.01, "1": 0.01, "2": 0.01, "3": 0.01, "4": 0.01,
            "5": 0.02, "6": 0.03, "7": 0.05, "8": 0.07, "9": 0.07,
            "10": 0.06, "11": 0.06, "12": 0.08, "13": 0.06, "14": 0.05,
            "15": 0.05, "16": 0.05, "17": 0.06, "18": 0.07, "19": 0.07,
            "20": 0.07, "21": 0.09, "22": 0.04, "23": 0.02
        }
    }

# 메인 컨텐츠
tab1, tab2, tab3 = st.tabs(["📝 게시물 설정", "🎯 단계별 설정", "📈 시뮬레이션 실행"])

with tab1:
    st.header("📝 게시물 설정")
    
    # 고급 설정 (접을 수 있는 섹션)
    with st.expander("⚙️ 고급 설정", expanded=False):
        # 기본 설정
        st.subheader("기본 설정")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.simulation_config['seed'] = st.number_input("시드", value=st.session_state.simulation_config['seed'], help="동일한 시드로 동일한 결과를 얻을 수 있습니다.")
        with col2:
            st.session_state.simulation_config['timezone'] = st.selectbox("시간대", ["Asia/Seoul"], 
                                                                         index=0, disabled=True)
        
        # 제한 설정
        st.subheader("제한 설정")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.simulation_config['max_hours'] = col1.number_input("최대 시뮬레이션 시간(시간)", value=st.session_state.simulation_config['max_hours'], min_value=1, help="최대 14일")
        with col2:
            st.session_state.simulation_config['system_hour_cap'] = st.number_input("시간당 상한", value=st.session_state.simulation_config['system_hour_cap'], min_value=1, help="선택사항")
        
        # 시간 간격 설정
        st.subheader("시간 간격 설정")
        st.session_state.simulation_config['tick_type'] = st.radio("증분 주기", ["고정", "랜덤 범위"], 
                                                                 index=0 if st.session_state.simulation_config['tick_type'] == "고정" else 1)
        
        if st.session_state.simulation_config['tick_type'] == "고정":
            st.session_state.simulation_config['tick_duration'] = st.text_input("고정 간격", value=st.session_state.simulation_config['tick_duration'], help="예: 1h, 30m, 15s")
        else:
            col1, col2 = st.columns(2)
            with col1:
                st.session_state.simulation_config['tick_min'] = col1.text_input("최소 간격", value=st.session_state.simulation_config['tick_min'])
            with col2:
                st.session_state.simulation_config['tick_max'] = col2.text_input("최대 간격", value=st.session_state.simulation_config['tick_max'])
        
        # 조회수 증분 설정
        st.subheader("조회수 증분 설정")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.simulation_config['inc_min'] = col1.number_input("최소 증분", value=st.session_state.simulation_config['inc_min'], min_value=1)
        with col2:
            st.session_state.simulation_config['inc_max'] = col2.number_input("최대 증분", value=st.session_state.simulation_config['inc_max'], min_value=1)
    
    st.markdown("---")
    
    # 대량 게시물 생성
    st.subheader("📦 대량 게시물 생성")
    st.markdown("시간대별 가중치에 따라 게시물의 시작 시간이 랜덤하게 분산됩니다.")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        # 시작 날짜만 설정
        if 'new_date' not in st.session_state:
            st.session_state.new_date = datetime.now().date()
        
        new_date = st.date_input("시작 날짜", value=st.session_state.new_date, key="new_date_input")
        st.session_state.new_date = new_date
    
    with col2:
        # 단계 선택
        selected_stage = st.selectbox("게시물 단계", range(1, 14), index=6, help="생성할 게시물의 단계를 선택하세요")
    
    with col3:
        # 생성 개수
        post_count = st.number_input("생성 개수", value=1, min_value=1, max_value=100, help="생성할 게시물 개수")
        
        # 시드 오프셋 설정
        seed_offset = st.number_input("시드 오프셋", value=0, help="각 게시물의 시드 오프셋")
        
        # 생성 버튼
        if st.button(f"🚀 {post_count}개 게시물 생성", type="primary"):
            if 'posts_data' not in st.session_state:
                st.session_state.posts_data = []
            
            # 다음 ID 계산
            if not st.session_state.posts_data:
                next_id = 1001
            else:
                existing_ids = [int(post['post_id']) for post in st.session_state.posts_data if post['post_id'].isdigit()]
                next_id = max(existing_ids) + 1 if existing_ids else 1001
            
            # 시간대별 가중치 기반 랜덤 시간 생성
            import random
            
            def generate_random_time():
                # 시간대별 가중치 가져오기
                weights = st.session_state.simulation_config['hourly_weights']
                
                # 가중치를 리스트로 변환 (0-23시)
                hour_weights = [weights.get(str(hour), 0.01) for hour in range(24)]
                
                # 가중치 기반으로 시간 선택
                selected_hour = random.choices(range(24), weights=hour_weights)[0]
                
                # 분과 초는 랜덤하게 (0-59분, 0-59초)
                selected_minute = random.randint(0, 59)
                selected_second = random.randint(0, 59)
                
                return selected_hour, selected_minute, selected_second
            
            # 게시물 생성
            created_posts = []
            
            for i in range(post_count):
                # 랜덤 시간 생성
                hour, minute, second = generate_random_time()
                
                # 시작 날짜와 랜덤 시간 결합
                start_datetime = datetime.combine(new_date, datetime.min.time().replace(hour=hour, minute=minute, second=second))
                
                st.session_state.posts_data.append({
                    'post_id': str(next_id),
                    'stage': selected_stage,
                    'cum_views': 0,
                    'start_datetime': start_datetime.strftime("%Y-%m-%d %H:%M:%S"),
                    'seed_offset': seed_offset
                })
                created_posts.append(f"{next_id}번 ({selected_stage}단계, {start_datetime.strftime('%H:%M:%S')})")
                next_id += 1
            
            st.success(f"✅ {post_count}개 게시물이 생성되었습니다!")
            st.info(f"생성된 게시물: {', '.join(created_posts[:10])}{'...' if len(created_posts) > 10 else ''}")
            
            # 시간대별 분포 표시
            hour_distribution = {}
            for post in created_posts:
                hour = int(post.split(', ')[1].split(':')[0])
                hour_distribution[hour] = hour_distribution.get(hour, 0) + 1
            
            st.markdown("**시간대별 분포:**")
            for hour in sorted(hour_distribution.keys()):
                count = hour_distribution[hour]
                weight = st.session_state.simulation_config['hourly_weights'].get(str(hour), 0.01)
                st.write(f"{hour:02d}시: {count}개 (가중치: {weight:.2f})")
    
    # 기존 단일 게시물 추가 기능 (숨김)
    with st.expander("🔧 고급: 단일 게시물 추가", expanded=False):
        st.markdown("*개발자용 기능입니다. 일반적으로는 위의 대량 생성 기능을 사용하세요.*")
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            # 자동으로 다음 ID 생성
            if 'posts_data' not in st.session_state or not st.session_state.posts_data:
                next_id = "1001"
            else:
                existing_ids = [int(post['post_id']) for post in st.session_state.posts_data if post['post_id'].isdigit()]
                next_id = str(max(existing_ids) + 1) if existing_ids else "1001"
            
            st.text_input("게시물 ID", value=next_id, disabled=True, help="자동으로 생성되는 고유 ID입니다")
            new_post_id = next_id
        
        with col2:
            new_stage = st.selectbox("단계", range(1, 14), index=6, key="single_stage")
        
        with col3:
            # new_time 초기화 확인
            if 'new_time' not in st.session_state:
                st.session_state.new_time = datetime.now().time()
            
            single_date = st.date_input("시작 날짜", value=st.session_state.new_date, key="single_date")
            single_time = st.time_input("시작 시간", value=st.session_state.new_time, key="single_time")
            single_start_time = datetime.combine(single_date, single_time)
        
        with col4:
            single_seed_offset = st.number_input("시드 오프셋", value=0, key="single_seed")
        
        if st.button("게시물 추가", key="single_add"):
            if 'posts_data' not in st.session_state:
                st.session_state.posts_data = []
            
            st.session_state.posts_data.append({
                'post_id': new_post_id,
                'stage': new_stage,
                'cum_views': 0,
                'start_datetime': single_start_time.strftime("%Y-%m-%d %H:%M:%S"),
                'seed_offset': single_seed_offset
            })
            
            st.success(f"✅ 게시물 {new_post_id}이 추가되었습니다!")
    
    # 게시물 목록 표시
    if 'posts_data' in st.session_state and st.session_state.posts_data:
        st.subheader("게시물 목록")
        posts_df = pd.DataFrame(st.session_state.posts_data)
        
        # 삭제할 게시물 선택
        if len(st.session_state.posts_data) > 0:
            delete_options = [f"{post['post_id']} (단계 {post['stage']})" for post in st.session_state.posts_data]
            
            col1, col2 = st.columns([4, 1])
            with col1:
                selected_delete = st.selectbox("삭제할 게시물 선택", delete_options, key="delete_select")
            with col2:
                st.markdown("<br>", unsafe_allow_html=True)  # 버튼을 드롭다운과 같은 높이로 맞춤
                if st.button("🗑️ 삭제", type="secondary", use_container_width=True):
                    # 선택된 게시물의 인덱스 찾기
                    selected_index = delete_options.index(selected_delete)
                    deleted_post = st.session_state.posts_data.pop(selected_index)
                    st.success(f"✅ 게시물 {deleted_post['post_id']}이 삭제되었습니다!")
                    st.rerun()
        
        st.dataframe(posts_df, use_container_width=True)
    else:
        st.info("게시물을 추가해주세요.")

with tab2:
    st.header("🎯 단계별 설정")
    
    # 시간대별 가중치 설정
    st.subheader("⏰ 시간대별 가중치")
    st.markdown("각 시간대의 조회수 증가 비율을 설정하세요. 높을수록 해당 시간대에 조회수가 많이 증가합니다.")
    
    # 현재 가중치 시각화
    weights_data = []
    for hour in range(24):
        weight = st.session_state.simulation_config['hourly_weights'].get(str(hour), 0.01)
        weights_data.append({
            '시간': f"{hour:02d}시",
            '가중치': weight,
            '시간대': hour
        })
    
    weights_df = pd.DataFrame(weights_data)
    
    # 막대 차트로 가중치 시각화
    fig = px.bar(weights_df, x='시간', y='가중치', 
                 title='시간대별 조회수 증가 가중치',
                 color='가중치',
                 color_continuous_scale='Blues')
    fig.update_layout(height=300, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)
    
    # 시간대별 가중치 입력 (6열로 배치하여 더 컴팩트하게)
    st.markdown("**가중치 조정:**")
    cols = st.columns(6)
    for hour in range(24):
        col_idx = hour % 6
        with cols[col_idx]:
            current_value = st.session_state.simulation_config['hourly_weights'].get(str(hour), 0.01)
            
            # 시간대별 색상 구분
            if 6 <= hour <= 11:  # 오전
                color = "🟡"
            elif 12 <= hour <= 17:  # 오후
                color = "🟠"
            elif 18 <= hour <= 23:  # 저녁
                color = "🔴"
            else:  # 새벽
                color = "🌙"
            
            st.session_state.simulation_config['hourly_weights'][str(hour)] = st.number_input(
                f"{color} {hour:02d}시", 
                value=current_value, 
                min_value=0.0, 
                step=0.01, 
                key=f"weight_{hour}",
                help=f"{hour:02d}시 조회수 증가 비율"
            )
    
    # 가중치 요약 정보
    total_weight = sum(st.session_state.simulation_config['hourly_weights'].values())
    max_weight = max(st.session_state.simulation_config['hourly_weights'].values())
    max_hour = max(st.session_state.simulation_config['hourly_weights'].items(), key=lambda x: x[1])[0]
    
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("총 가중치", f"{total_weight:.2f}")
    with col2:
        st.metric("최고 가중치", f"{max_weight:.2f}")
    with col3:
        st.metric("최고 시간대", f"{max_hour}시")
    
    st.markdown("---")
    
    # 단계별 목표 조회수 설정
    st.subheader("📊 단계별 목표 조회수 설정")
    
    # stages.yml의 실제 값들
    default_stages = {
        "1": {"views_min": 10, "views_max": 50},
        "2": {"views_min": 50, "views_max": 100},
        "3": {"views_min": 100, "views_max": 150},
        "4": {"views_min": 150, "views_max": 300},
        "5": {"views_min": 300, "views_max": 500},
        "6": {"views_min": 500, "views_max": 800},
        "7": {"views_min": 800, "views_max": 1000},
        "8": {"views_min": 1000, "views_max": 1500},
        "9": {"views_min": 1500, "views_max": 2500},
        "10": {"views_min": 2500, "views_max": 4000},
        "11": {"views_min": 4000, "views_max": 6000},
        "12": {"views_min": 6000, "views_max": 8000},
        "13": {"views_min": 8000, "views_max": 10000}
    }
    
    stages_data = {}
    for stage in range(1, 14):
        col1, col2 = st.columns(2)
        stage_key = str(stage)
        default_min = default_stages[stage_key]["views_min"]
        default_max = default_stages[stage_key]["views_max"]
        
        with col1:
            min_views = col1.number_input(f"{stage}단계 최소 조회수", value=default_min, min_value=1, key=f"stage_{stage}_min")
        with col2:
            max_views = col2.number_input(f"{stage}단계 최대 조회수", value=default_max, min_value=min_views, key=f"stage_{stage}_max")
        
        stages_data[str(stage)] = {
            'views_min': min_views,
            'views_max': max_views
        }
    
    # 단계별 설정 미리보기
    st.subheader("단계별 설정 미리보기")
    stages_df = pd.DataFrame([
        {
            '단계': stage,
            '최소 조회수': data['views_min'],
            '최대 조회수': data['views_max'],
            '평균 조회수': (data['views_min'] + data['views_max']) // 2
        }
        for stage, data in stages_data.items()
    ])
    st.dataframe(stages_df, use_container_width=True)

with tab3:
    st.header("시뮬레이션 실행")
    
    if 'posts_data' not in st.session_state or not st.session_state.posts_data:
        st.warning("먼저 게시물을 추가해주세요.")
    else:
        if st.button("🚀 시뮬레이션 실행", type="primary"):
            with st.spinner("시뮬레이션을 실행 중입니다..."):
                try:
                    # 임시 파일 생성
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as posts_file:
                        posts_df = pd.DataFrame(st.session_state.posts_data)
                        posts_df.to_csv(posts_file.name, index=False)
                        posts_path = posts_file.name
                    
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as stages_file:
                        stages_config = {'stages': stages_data}
                        yaml.dump(stages_config, stages_file, default_flow_style=False, allow_unicode=True)
                        stages_path = stages_file.name
                    
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.yml', delete=False) as engine_file:
                        config = st.session_state.simulation_config
                        engine_config = {
                            'timezone': config['timezone'],
                            'tick_duration': config['tick_duration'] if config['tick_type'] == "고정" else {
                                'min': config['tick_min'],
                                'max': config['tick_max']
                            },
                            'increment': {
                                'min': config['inc_min'],
                                'max': config['inc_max']
                            },
                            'hourly_weights': config['hourly_weights'],
                            'limits': {
                                'max_hours': config['max_hours'],
                                'system_hour_cap': config['system_hour_cap'] if config['system_hour_cap'] else None
                            }
                        }
                        yaml.dump(engine_config, engine_file, default_flow_style=False, allow_unicode=True)
                        engine_path = engine_file.name
                    
                    with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as output_file:
                        output_path = output_file.name
                    
                    # 시뮬레이션 실행
                    simulate(posts_path, stages_path, engine_path, output_path, st.session_state.simulation_config['seed'])
                    
                    # 결과 읽기
                    result_df = pd.read_csv(output_path)
                    result_df['datetime'] = pd.to_datetime(result_df['datetime'])
                    
                    # 세션에 결과 저장
                    st.session_state.simulation_result = result_df
                    
                    # 임시 파일 삭제
                    os.unlink(posts_path)
                    os.unlink(stages_path)
                    os.unlink(engine_path)
                    os.unlink(output_path)
                    
                    st.success("시뮬레이션이 완료되었습니다!")
                    
                except Exception as e:
                    st.error(f"시뮬레이션 실행 중 오류가 발생했습니다: {str(e)}")
        
        # 결과 표시
        if 'simulation_result' in st.session_state:
            result_df = st.session_state.simulation_result
            
            st.subheader("📊 시뮬레이션 결과")
            
            # 요약 통계
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("총 게시물 수", len(result_df['post_id'].unique()))
            with col2:
                st.metric("총 시뮬레이션 시간", f"{len(result_df)} 시간")
            with col3:
                st.metric("총 조회수 증가", f"{result_df['views_inc'].sum():,}")
            with col4:
                st.metric("평균 시간당 증가", f"{result_df['views_inc'].mean():.1f}")
            
            # 차트
            st.subheader("📈 조회수 증가 추이")
            
            # 게시물별 누적 조회수 차트
            fig_cumulative = px.line(result_df, x='datetime', y='cum_views', color='post_id',
                                   title='게시물별 누적 조회수 추이')
            fig_cumulative.update_layout(height=500)
            st.plotly_chart(fig_cumulative, use_container_width=True)
            
            # 시간대별 조회수 증가량 히트맵
            result_df['hour'] = result_df['datetime'].dt.hour
            hourly_inc = result_df.groupby(['post_id', 'hour'])['views_inc'].sum().reset_index()
            
            fig_heatmap = px.density_heatmap(hourly_inc, x='hour', y='post_id', z='views_inc',
                                           title='시간대별 조회수 증가량 히트맵')
            fig_heatmap.update_layout(height=400)
            st.plotly_chart(fig_heatmap, use_container_width=True)
            
            # 게시물별 최종 조회수 막대 차트
            final_views = result_df.groupby('post_id')['cum_views'].max().reset_index()
            fig_bar = px.bar(final_views, x='post_id', y='cum_views',
                           title='게시물별 최종 조회수')
            fig_bar.update_layout(height=400)
            st.plotly_chart(fig_bar, use_container_width=True)
            
            # 상세 데이터 표시
            st.subheader("📋 상세 결과 데이터")
            st.dataframe(result_df, use_container_width=True)
            
            # CSV 다운로드
            csv = result_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 CSV 다운로드",
                data=csv,
                file_name=f"simulation_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )

# 푸터
st.markdown("---")
st.markdown("**AUTO_BORAD2** - 게시물 조회수 시뮬레이션 도구")

